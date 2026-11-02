import base64
import logging
import json
import subprocess
import secrets
import time
from collections import defaultdict, deque
from contextlib import asynccontextmanager
from datetime import UTC, timedelta

from cryptography.exceptions import InvalidSignature
from fastapi import Depends, FastAPI, HTTPException
from fastapi.responses import JSONResponse
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import create_engine, func, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, sessionmaker

from . import schemas as s
from .config import Settings
from .crypto import canonical, digest, load_signer, public_key, signed_document
from .vpn_control import Controller
from .models import (
    VpnClient,
    VpnEnrollment,
    VpnDeletion,
    ActivationToken,
    Administrator,
    AuditLog,
    Challenge,
    Customer,
    Device,
    DeviceKey,
    DeviceSession,
    Installation,
    License,
    LicenseBinding,
    RegistrationEvent,
    now,
    uid,
)

log = logging.getLogger("kdx.registration")
log.setLevel(logging.INFO)
log.addHandler(logging.StreamHandler())
log.propagate = False
bearer = HTTPBearer(auto_error=False)


def utc(value):
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value


def create_app(settings=None, engine=None, signer=None, vpn_controller=None):
    cfg = settings or Settings()
    engine = engine or create_engine(cfg.database_url, pool_pre_ping=True)
    sessions = sessionmaker(engine, expire_on_commit=False)

    @asynccontextmanager
    async def lifespan(app):
        if app.state.signer is None:
            app.state.signer = load_signer(cfg.signing_key)
        yield

    app = FastAPI(title="KDX InfraBox Registration", version="1.0.0", lifespan=lifespan)
    app.state.signer = signer
    app.state.sessions = sessions
    app.state.vpn_controller = vpn_controller or Controller(cfg)
    buckets = defaultdict(deque)

    @app.middleware("http")
    async def guard(request, call_next):
        request_id = uid()
        # No forwarded headers are trusted. Deployment uses a single worker.
        ip = request.client.host if request.client else "unknown"
        if request.url.path != "/health":
            if not cfg.allow_lab_http and request.url.scheme != "https":
                return JSONResponse({"detail": "HTTPS required"}, status_code=400)
            if len(buckets) > 10000:
                cutoff = time.monotonic() - 60
                for key in list(buckets):
                    if not buckets[key] or buckets[key][-1] < cutoff:
                        del buckets[key]
                if len(buckets) > 10000 and ip not in buckets:
                    return JSONResponse({"detail": "Rate limit capacity reached"}, status_code=429)
            bucket = buckets[ip]
            tick = time.monotonic()
            while bucket and bucket[0] < tick - 60:
                bucket.popleft()
            if len(bucket) >= cfg.rate_per_minute:
                return JSONResponse(
                    {"detail": "Rate limit exceeded"},
                    status_code=429,
                    headers={"Retry-After": "60"},
                )
            bucket.append(tick)
            length = request.headers.get("content-length")
            if length and (not length.isdigit() or int(length) > 16384):
                return JSONResponse({"detail": "Request too large"}, status_code=413)
            # Also bounds chunked requests; never log request bodies or credentials.
            total = 0
            chunks = []
            async for chunk in request.stream():
                total += len(chunk)
                if total > 16384:
                    return JSONResponse({"detail": "Request too large"}, status_code=413)
                chunks.append(chunk)
            request._body = b"".join(chunks)
        response = await call_next(request)
        response.headers["X-Request-ID"] = request_id
        response.headers["Cache-Control"] = "no-store"
        log.info(
            canonical(
                {
                    "request_id": request_id,
                    "method": request.method,
                    "path": request.url.path,
                    "status": response.status_code,
                }
            )
        )
        return response

    def db():
        with sessions() as session:
            try:
                # Serialize short state transitions across processes, including first enrollment.
                # This avoids missing-row races and inconsistent capacity checks.
                if engine.dialect.name == "postgresql":
                    session.execute(text("SELECT pg_advisory_xact_lock(1464096837)"))
                yield session
                session.commit()
            except IntegrityError:
                session.rollback()
                raise HTTPException(409, "Concurrent identity conflict; retry enrollment") from None

    def audit(session, actor, action, target, detail):
        session.add(AuditLog(actor=actor, action=action, target=target, detail=detail))

    def event(session, device, kind, detail):
        session.add(
            RegistrationEvent(device_id=device.id if device else None, kind=kind, detail=detail)
        )
        audit(session, "device", kind, device.id if device else "unknown", detail)

    def reject(session, device, kind, detail, status=403):
        event(session, device, kind, detail)
        session.commit()  # Persist security events and consumed challenges even on HTTP errors.
        raise HTTPException(status, kind)

    def admin(
        credentials: HTTPAuthorizationCredentials | None = Depends(bearer),
        session: Session = Depends(db, scope="function"),
    ):
        value = session.scalar(
            select(Administrator).where(
                Administrator.token_hash == digest(credentials.credentials if credentials else "")
            )
        )
        if not value or not value.active or utc(value.expires_at) <= now():
            reject(session, None, "ADMIN_AUTH_DENIED", {}, 401)
        return value

    def writer(actor: Administrator = Depends(admin)):
        if actor.role != "admin":
            raise HTTPException(403, "Administrator role required")
        return actor

    def get_device(session, device_id):
        value = session.get(Device, str(device_id))
        if not value:
            raise HTTPException(404, "Device not found")
        return value

    def license_for(session, device):
        binding = session.get(LicenseBinding, device.id)
        return session.get(License, binding.license_id) if binding else None

    def state(session, device):
        if device.archived_at:
            return "REVOKED"
        if device.status in {"REVOKED", "SUSPENDED", "PENDING", "ACTIVATION_REQUIRED"}:
            return device.status
        lic = license_for(session, device)
        if not lic:
            return "ACTIVATION_REQUIRED"
        if lic.status != "ACTIVE":
            return lic.status
        if lic.expires_at and utc(lic.expires_at) <= now():
            return "EXPIRED"
        return "ACTIVE"

    def identity(session, value):
        inst = session.get(Installation, str(value.installation_id))
        key = session.scalar(select(DeviceKey).where(DeviceKey.public_key == value.public_key))
        if inst:
            device = get_device(session, inst.device_id)
            if device.serial != value.serial:
                reject(session, device, "HARDWARE_MISMATCH", {"observed_serial": value.serial})
            if not key or key.installation_id != inst.id:
                reject(session, device, "IDENTITY_MISMATCH", {})
            return device, inst, key
        if key:
            reject(
                session,
                get_device(session, session.get(Installation, key.installation_id).device_id),
                "KEY_REUSE",
                {},
            )
        return None, None, None

    def consume(session, value, purpose):
        challenge = session.get(Challenge, str(value.challenge_id))
        if not challenge or challenge.used_at or utc(challenge.expires_at) <= now():
            reject(session, None, "INVALID_OR_REPLAYED_CHALLENGE", {}, 401)
        challenge.used_at = now()
        device = get_device(session, challenge.device_id)
        if challenge.purpose != purpose:
            reject(session, device, "WRONG_CHALLENGE_PURPOSE", {}, 401)
        key = session.get(DeviceKey, challenge.key_id)
        try:
            public_key(key.public_key).verify(
                base64.b64decode(value.signature), challenge.message.encode()
            )
        except (InvalidSignature, ValueError):
            reject(session, device, "INVALID_SIGNATURE", {}, 401)
        if challenge.serial != device.serial:
            reject(session, device, "HARDWARE_MISMATCH", {})
        return device, session.get(Installation, challenge.installation_id), key

    def identity_status(session, device, inst, key):
        if device.archived_at:
            return "REVOKED"
        status = state(session, device)
        if not inst.current or not key.current:
            pending_token = session.scalar(
                select(ActivationToken).where(
                    ActivationToken.installation_id == inst.id,
                    ActivationToken.key_id == key.id,
                    ActivationToken.used_at.is_(None),
                    ActivationToken.expires_at > now(),
                )
            )
            status = "ACTIVATION_REQUIRED" if pending_token else "PENDING"
        return status

    def authorize(session, device, inst, key):
        status = identity_status(session, device, inst, key)
        result = {
            "device_id": device.id,
            "status": status,
            "ssid": "infrabox-" + device.serial[-8:],
        }
        if status == "ACTIVE":
            lic = license_for(session, device)
            issued = now()
            expires = issued + timedelta(seconds=cfg.offline_grace_seconds)
            if lic.expires_at:
                expires = min(expires, utc(lic.expires_at))
            lic.last_validated_at = issued
            device.last_seen = issued
            payload = {
                "v": 1,
                "aud": cfg.audience,
                "device_id": device.id,
                "serial": device.serial,
                "installation_id": inst.id,
                "key_hash": digest(key.public_key),
                "license_id": lic.id,
                "status": "ACTIVE",
                "issued_at": int(issued.timestamp()),
                "expires_at": int(expires.timestamp()),
            }
            result["authorization"] = signed_document(app.state.signer, payload)
            token = secrets.token_urlsafe(32)
            session.add(
                DeviceSession(
                    token_hash=digest(token),
                    device_id=device.id,
                    installation_id=inst.id,
                    key_id=key.id,
                    expires_at=issued + timedelta(seconds=cfg.device_session_seconds),
                )
            )
            result["session_token"] = token
        return result

    def device_session(
        credentials: HTTPAuthorizationCredentials | None = Depends(bearer),
        session: Session = Depends(db, scope="function"),
    ):
        value = session.get(DeviceSession, digest(credentials.credentials if credentials else ""))
        if not value or utc(value.expires_at) <= now():
            raise HTTPException(401, "Valid device session required")
        device = get_device(session, value.device_id)
        inst = session.get(Installation, value.installation_id)
        key = session.get(DeviceKey, value.key_id)
        if not inst.current or not key.current:
            raise HTTPException(403, "Identity no longer bound")
        return device, inst, key

    @app.get("/health")
    def health():
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))
        return {"status": "ok", "service": "kdx-registration", "version": "1.0.0"}

    @app.post("/api/v1/devices/enroll")
    def enroll(value: s.Enroll, session: Session = Depends(db, scope="function")):
        device, inst, key = identity(session, value)
        if not inst:
            device = session.scalar(select(Device).where(Device.serial == value.serial))
            if not device:
                device = Device(serial=value.serial, model=value.model, firmware=value.firmware)
                session.add(device)
                session.flush()
            inst = Installation(id=str(value.installation_id), device_id=device.id)
            session.add(inst)
            session.flush()
            key = DeviceKey(installation_id=inst.id, public_key=value.public_key)
            session.add(key)
            event(session, device, "ENROLLMENT_REQUESTED", {"installation_id": inst.id})
        result = {
            "device_id": device.id,
            "installation_id": inst.id,
            "status": identity_status(session, device, inst, key),
            "ssid": "infrabox-" + value.serial[-8:],
        }
        return result

    @app.post("/api/v1/devices/challenge")
    def challenge(value: s.ChallengeInput, session: Session = Depends(db, scope="function")):
        device, inst, key = identity(session, value)
        if not inst:
            raise HTTPException(404, "Enroll first")
        ident = uid()
        expires = now() + timedelta(seconds=cfg.challenge_seconds)
        message = canonical(
            {
                **({"vpn_request_hash": digest(canonical(value.vpn_request.model_dump(mode="json"))), "vpn_operation": value.vpn_operation} if value.purpose == "vpn" else {}),
                "v": 1,
                "aud": cfg.audience,
                "challenge_id": ident,
                "nonce": secrets.token_urlsafe(32),
                "serial": value.serial,
                "installation_id": inst.id,
                "key_hash": digest(key.public_key),
                "purpose": value.purpose,
                "expires_at": int(expires.timestamp()),
            }
        )
        session.add(
            Challenge(
                id=ident,
                device_id=device.id,
                installation_id=inst.id,
                key_id=key.id,
                serial=value.serial,
                purpose=value.purpose,
                message=message,
                expires_at=expires,
            )
        )
        return {"challenge_id": ident, "message": message, "expires_at": expires}

    def vpn_summary(session, item):
        device = get_device(session, item.device_id)
        return {"id": item.id, "device_id": device.id, "serial": device.serial,
                "device_name": device.display_name or device.model,
                "customer": customer_summary(session.get(Customer, device.customer_id)) if device.customer_id else None,
                "installation_id": item.installation_id, "public_key": item.public_key,
                "request": item.request, "registration": item.registration,
                "status": item.status, "updated_at": item.updated_at}

    def vpn_remote(action, request):
        try:
            return app.state.vpn_controller.apply(action, request)
        except (ValueError, OSError, TimeoutError, subprocess.TimeoutExpired):
            raise HTTPException(503, "VPN operation unconfirmed; retry the same action to reconcile") from None

    def retire_vpn(session, item, actor, reason):
        result = vpn_remote("delete", item.request)
        if result.get("status") != "DELETED":
            raise HTTPException(503, "VPN deletion unconfirmed; retry to reconcile")
        old = session.get(VpnDeletion, item.request["request_id"])
        if not old:
            session.add(VpnDeletion(request_id=item.request["request_id"], device_id=item.device_id,
                installation_id=item.installation_id, key_id=item.key_id,
                public_key=item.public_key, request=item.request))
        item.status, item.registration, item.updated_at = "ARCHIVED", None, now()
        audit(session, actor, "VPN_DELETED", item.id,
            {"device_id":item.device_id,"request_id":item.request["request_id"],"reason":reason})
        session.flush()

    def vpn_deleted_document(device, request):
        issued = int(now().timestamp())
        return {"status":"DELETED", "document":signed_document(app.state.signer, {
            "v":1,"aud":"kdx-infrabox-vpn-state","status":"DELETED","serial":device.serial,
            "request":request,"issued_at":issued,"expires_at":issued+600})}

    @app.post("/api/v1/devices/vpn")
    def vpn_request(value: s.VpnProof, session: Session = Depends(db, scope="function")):
        device, inst, key = consume(session, value, "vpn")
        challenge = session.get(Challenge, str(value.challenge_id))
        message = json.loads(challenge.message)
        request = value.request.model_dump(mode="json")
        if (message.get("vpn_request_hash") != digest(canonical(request))
                or message.get("vpn_operation", "sync") != value.operation):
            reject(session, device, "VPN_REQUEST_MISMATCH", {}, 401)
        if request["device_id"].upper() != device.serial:
            reject(session, device, "HARDWARE_MISMATCH", {})
        deleted = session.get(VpnDeletion, request["request_id"])
        if deleted:
            if (deleted.device_id != device.id or deleted.installation_id != inst.id
                    or deleted.key_id != key.id or deleted.request != request):
                reject(session, device, "VPN_RECOVERY_REQUIRED", {}, 409)
            # A delayed request belongs to the retired generation, never its replacement.
            return vpn_deleted_document(device, request)
        item = session.scalar(select(VpnEnrollment).where(VpnEnrollment.device_id == device.id))
        same = item and item.installation_id == inst.id and item.key_id == key.id and item.request == request
        if value.operation == "delete":
            if item and not same:
                reject(session, device, "VPN_RECOVERY_REQUIRED", {}, 409)
            if item:
                retire_vpn(session, item, "device", "Deletion requested on InfraBox")
            else:
                # This generation never acquired a central grant, so has no peer
                # the device is entitled to mutate. Retire its local request only.
                session.add(VpnDeletion(request_id=request["request_id"], device_id=device.id,
                    installation_id=inst.id,key_id=key.id,public_key=request["public_key"],request=request))
                audit(session,"device","VPN_DELETED",device.id,{"request_id":request["request_id"]})
            return vpn_deleted_document(device, request)
        if same and item.status == "ARCHIVED":
            # Upgrade old archive records to actual peer deletion and cleanup.
            retire_vpn(session, item, "system", "Retired VPN grant cleanup")
            return vpn_deleted_document(device, request)
        if item and item.status != "ARCHIVED" and not same:
            reject(session, device, "VPN_RECOVERY_REQUIRED", {}, 409)
        if device.archived_at:
            reject(session, device, "VPN_DEVICE_ARCHIVED", {})
        if not item or item.status == "ARCHIVED":
            if not item:
                observed = vpn_remote("inspect", request)
                if observed.get("status") == "DELETED":
                    # Old installations could leave an archived server record after
                    # the dashboard grant disappeared. Retire that exact generation.
                    removed = vpn_remote("delete", request)
                    if removed.get("status") != "DELETED":
                        raise HTTPException(503,"VPN deletion unconfirmed")
                    session.add(VpnDeletion(request_id=request["request_id"],device_id=device.id,
                        installation_id=inst.id,key_id=key.id,public_key=request["public_key"],request=request))
                    audit(session,"system","VPN_DELETED",device.id,{"request_id":request["request_id"],"reason":"Old archived peer cleanup"})
                    return vpn_deleted_document(device,request)
                if observed.get("status") not in {"MISSING","PRESENT"}:
                    raise HTTPException(503,"VPN peer state could not be verified")
            if session.scalar(select(VpnDeletion.request_id).where(VpnDeletion.public_key == request["public_key"])):
                reject(session,device,"VPN_FRESH_KEY_REQUIRED",{},409)
            if not item:
                item = VpnEnrollment(device_id=device.id)
                session.add(item)
            item.installation_id, item.key_id, item.public_key = inst.id, key.id, request["public_key"]
            item.request, item.registration, item.status, item.updated_at = request, None, "PENDING", now()
            session.flush()
            audit(session, "device", "VPN_REQUESTED", item.id,
                {"device_id":device.id,"request_id":request["request_id"]})
        if item.status in {"ACTIVE", "SUSPENDED"}:
            observed = vpn_remote("inspect", item.request)
            if observed.get("status") in {"MISSING", "DELETED"}:
                retire_vpn(session,item,"system","Managed peer deleted on VPN server")
                return vpn_deleted_document(device,request)
            if observed.get("status") != "PRESENT":
                raise HTTPException(503,"VPN peer state could not be verified")
        result = {"id": item.id, "status": item.status}
        if item.status == "ACTIVE":
            issued = int(now().timestamp())
            result["document"] = signed_document(app.state.signer, {
                "v": 1, "aud": "kdx-infrabox-vpn", "status": "ACTIVE",
                "serial": device.serial, "registration": item.registration,
                "issued_at": issued, "expires_at": issued + 600})
        return result

    @app.get("/api/v1/admin/vpn")
    def vpn_list(actor=Depends(admin), session: Session = Depends(db, scope="function")):
        return [vpn_summary(session, item) for item in session.scalars(
            select(VpnEnrollment).where(VpnEnrollment.status != "ARCHIVED").order_by(VpnEnrollment.created_at.desc()).limit(200))]

    @app.post("/api/v1/admin/vpn/{enrollment_id}/{action}")
    def vpn_action(enrollment_id: str, action: str, value: s.Reason, actor=Depends(writer),
                   session: Session = Depends(db, scope="function")):
        item = session.get(VpnEnrollment, enrollment_id)
        if not item or action not in {"approve", "suspend", "resume", "archive", "delete"}:
            raise HTTPException(404, "VPN request or action not found")
        device = get_device(session, item.device_id)
        if action in {"delete", "archive"}:
            retire_vpn(session,item,actor.name,value.reason)
            return {"id":item.id,"status":"DELETED"}
        if device.archived_at and action in {"approve", "resume"}:
            raise HTTPException(409, "Restore device before enabling VPN")
        if item.status == "ARCHIVED" and action != "archive":
            raise HTTPException(409, "Archived VPN grant cannot be enabled; operator recovery required")
        if item.status == "PENDING" and action in {"resume", "suspend"}:
            raise HTTPException(409, "Approve or archive the pending VPN request")
        try:
            result = app.state.vpn_controller.apply(action, item.request)
            expected = {"approve":"ACTIVE", "resume":"ACTIVE", "suspend":"SUSPENDED", "archive":"ARCHIVED"}[action]
            if result.get("status") != expected:
                raise ValueError("VPN state unconfirmed")
            registration = result.get("registration")
            if expected == "ACTIVE":
                if not isinstance(registration, dict) or any(registration.get(k) != v for k,v in item.request.items()):
                    raise ValueError("VPN response binding mismatch")
                item.registration = registration
        except (ValueError, OSError, TimeoutError, subprocess.TimeoutExpired):
            raise HTTPException(503, "VPN operation unconfirmed; retry the same action to reconcile") from None
        item.status, item.updated_at = expected, now()
        audit(session, actor.name, "VPN_"+action.upper(), item.id,
              {"device_id": device.id, "reason": value.reason})
        return vpn_summary(session, item)

    def vpn_client_summary(session, item):
        customer=session.get(Customer,item.customer_id) if item.customer_id else None
        return {"id":item.id,"name":item.name,"owner_name":item.owner_name,"email":item.email,
            "platform":item.platform,"customer_id":item.customer_id,
            "customer":{"id":customer.id,"name":customer.name} if customer else None,
            "public_key":item.public_key,"status":item.status,"registration":item.registration,
            "created_at":item.created_at,"updated_at":item.updated_at}

    def client_change(session,item,action,actor,reason):
        result=vpn_remote(action,item.request)
        expected={"approve":"ACTIVE","resume":"ACTIVE","suspend":"SUSPENDED","delete":"DELETED"}[action]
        if result.get("status")!=expected:
            raise HTTPException(503,"VPN operation unconfirmed; retry the same action")
        if expected=="ACTIVE":
            registration=result.get("registration")
            if not isinstance(registration,dict) or any(registration.get(k)!=v for k,v in item.request.items()):
                raise HTTPException(503,"VPN response binding mismatch")
            item.registration=registration
        elif expected=="DELETED":item.registration=None
        item.status,item.updated_at=expected,now()
        audit(session,actor.name,"VPN_CLIENT_"+action.upper(),item.id,{"reason":reason})

    @app.get("/api/v1/admin/vpn-clients")
    def vpn_clients(actor=Depends(admin),session:Session=Depends(db,scope="function")):
        return [vpn_client_summary(session,item) for item in session.scalars(
            select(VpnClient).where(VpnClient.status!="DELETED").order_by(VpnClient.created_at.desc()).limit(200))]

    @app.post("/api/v1/admin/vpn-clients")
    def vpn_client_create(value:s.VpnClientInput,actor=Depends(writer),session:Session=Depends(db,scope="function")):
        ident=str(value.id)
        customer_id=str(value.customer_id) if value.customer_id else None
        if customer_id:active_customer(session,customer_id)
        item=session.get(VpnClient,ident)
        metadata={"name":value.name,"owner_name":value.owner_name,"email":value.email,
                  "platform":value.platform,"customer_id":customer_id,"public_key":value.public_key}
        if item:
            if any(getattr(item,k)!=v for k,v in metadata.items()) or item.status not in {"PENDING","ACTIVE"}:
                raise HTTPException(409,"Request already used; inspect the existing client")
            if item.status=="ACTIVE":return vpn_client_summary(session,item)
        else:
            if (session.scalar(select(VpnClient.id).where(VpnClient.public_key==value.public_key))
                    or session.scalar(select(VpnEnrollment.id).where(VpnEnrollment.public_key==value.public_key))
                    or session.scalar(select(VpnDeletion.request_id).where(VpnDeletion.public_key==value.public_key))):
                raise HTTPException(409,"VPN key already used; generate a fresh client key")
            request={"version":2,"client_id":ident,"hostname":"client-"+value.id.hex,
                     "public_key":value.public_key,"request_id":ident}
            item=VpnClient(id=ident,request=request,**metadata)
            session.add(item);session.flush()
            audit(session,actor.name,"VPN_CLIENT_CREATED",item.id,{"platform":item.platform})
        try:
            client_change(session,item,"approve",actor,"Desktop client creation")
        except HTTPException:
            # Keep public intent for retry/reconciliation if the SSH acknowledgment
            # was lost. The browser retains its key; this service never receives it.
            session.commit()
            raise
        return vpn_client_summary(session,item)

    @app.post("/api/v1/admin/vpn-clients/{client_id}/{action}")
    def vpn_client_action(client_id:str,action:str,value:s.Reason,actor=Depends(writer),
                          session:Session=Depends(db,scope="function")):
        item=session.get(VpnClient,client_id)
        if not item or action not in {"suspend","resume","delete"}:
            raise HTTPException(404,"Client or action not found")
        if item.status=="DELETED":
            if action=="delete":return {"id":item.id,"status":"DELETED"}
            raise HTTPException(409,"Deleted client requires fresh setup")
        if item.status=="PENDING" and action!="delete":
            raise HTTPException(409,"Retry client creation or delete the unconfirmed request")
        if action=="resume" and item.customer_id:active_customer(session,item.customer_id)
        client_change(session,item,action,actor,value.reason)
        return vpn_client_summary(session,item)

    @app.post("/api/v1/admin/vpn-peers/delete")
    def vpn_peer_delete(value:s.VpnPeerDelete,actor=Depends(writer),session:Session=Depends(db,scope="function")):
        item=session.scalar(select(VpnEnrollment).where(
            VpnEnrollment.public_key==value.public_key,VpnEnrollment.status!="ARCHIVED"))
        client=session.scalar(select(VpnClient).where(
            VpnClient.public_key==value.public_key,VpnClient.status!="DELETED"))
        selected=item or client
        if selected:
            registration=selected.registration or {}
            if value.allowed_ips!=[registration.get("address")]:
                raise HTTPException(409,"Peer address changed or is unconfirmed; refresh inventory or use its management section")
            if item:retire_vpn(session,item,actor.name,value.reason)
            else:client_change(session,client,"delete",actor,value.reason)
            return {"status":"DELETED"}
        result=vpn_remote("delete-unmanaged",{"version":3,"public_key":value.public_key,"allowed_ips":value.allowed_ips})
        if result.get("status")!="DELETED":raise HTTPException(503,"Peer deletion unconfirmed; refresh before retry")
        audit(session,actor.name,"VPN_PEER_DELETED",value.public_key,
              {"allowed_ips":value.allowed_ips,"reason":value.reason})
        return {"status":"DELETED"}

    def activate_binding(session, device, inst, key, token):
        # A per-license lock serializes capacity checks on PostgreSQL.
        if device.archived_at or device.status in {"REVOKED", "SUSPENDED"}:
            reject(session, device, device.status, {})
        lic = session.scalar(select(License).where(License.id == token.license_id).with_for_update())
        if not lic:
            reject(session, device, "LICENSE_UNAVAILABLE", {})
        token = session.scalar(
            select(ActivationToken).where(ActivationToken.id == token.id)
            .with_for_update().execution_options(populate_existing=True)
        )
        if utc(token.expires_at) <= now():
            reject(session, device, "INVALID_ACTIVATION_TOKEN", {}, 401)
        if token.used_at:
            return authorize(session, device, inst, key)
        active_customer(session, lic.customer_id)
        if lic.status != "ACTIVE" or (lic.expires_at and utc(lic.expires_at) <= now()):
            reject(session, device, "LICENSE_UNAVAILABLE", {})
        binding = session.get(LicenseBinding, device.id)
        if binding and binding.license_id != lic.id:
            reject(session, device, "ADMIN_REASSIGNMENT_REQUIRED", {}, 409)
        count = session.scalar(
            select(func.count())
            .select_from(LicenseBinding)
            .where(LicenseBinding.license_id == lic.id)
        )
        if not binding and count >= lic.max_devices:
            reject(session, device, "LICENSE_CAPACITY_REACHED", {}, 409)
        other = session.scalar(
            select(Installation).where(
                Installation.device_id == device.id, Installation.current.is_(True)
            )
        )
        if other and other.id != inst.id:
            reject(session, device, "ADMIN_RECOVERY_REQUIRED", {}, 409)
        if not binding:
            session.add(LicenseBinding(device_id=device.id, license_id=lic.id))
        inst.current = key.current = True
        device.status = "ACTIVE"
        device.customer_id = lic.customer_id
        token.used_at = now()
        session.flush()
        event(session, device, "ACTIVATED", {"license_id": lic.id, "installation_id": inst.id})
        return authorize(session, device, inst, key)

    @app.post("/api/v1/devices/verify")
    def verify(value: s.Proof, session: Session = Depends(db, scope="function")):
        device, inst, key = consume(session, value, "authenticate")
        approval = session.scalar(
            select(ActivationToken).where(
                ActivationToken.device_id == device.id,
                ActivationToken.installation_id == inst.id,
                ActivationToken.key_id == key.id,
                ActivationToken.automatic_activation.is_(True),
                ActivationToken.used_at.is_(None),
                ActivationToken.expires_at > now(),
            ).order_by(ActivationToken.expires_at.desc())
        )
        if approval:
            result = activate_binding(session, device, inst, key, approval)
        else:
            result = authorize(session, device, inst, key)
        event(session, device, "AUTHENTICATED", {"installation_id": inst.id})
        return result

    @app.post("/api/v1/devices/activate")
    def activate(value: s.Activate, session: Session = Depends(db, scope="function")):
        device, inst, key = consume(session, value, "activate")
        token = session.scalar(
            select(ActivationToken).where(
                ActivationToken.token_hash == digest(value.activation_token)
            )
        )
        if (
            not token
            or utc(token.expires_at) <= now()
            or token.device_id != device.id
            or token.installation_id != inst.id
            or token.key_id != key.id
        ):
            reject(session, device, "INVALID_ACTIVATION_TOKEN", {}, 401)
        if token.used_at:
            # A retry uses a fresh signed challenge. It can never rebind an old identity.
            if (
                inst.current
                and key.current
                and device.status == "ACTIVE"
                and license_for(session, device).id == token.license_id
            ):
                return authorize(session, device, inst, key)
            reject(session, device, "TOKEN_ALREADY_USED", {}, 409)
        return activate_binding(session, device, inst, key, token)

    @app.get("/api/v1/devices/status")
    def status(identity=Depends(device_session), session: Session = Depends(db, scope="function")):
        device, inst, key = identity
        return {
            "device_id": device.id,
            "status": state(session, device),
            "installation_id": inst.id,
        }

    @app.post("/api/v1/devices/heartbeat")
    def heartbeat(
        identity=Depends(device_session), session: Session = Depends(db, scope="function")
    ):
        return authorize(session, *identity)

    @app.post("/api/v1/admin/customers")
    def customer(
        value: s.CustomerInput,
        actor=Depends(writer),
        session: Session = Depends(db, scope="function"),
    ):
        item = Customer(**value.model_dump())
        session.add(item)
        session.flush()
        audit(session, actor.name, "CUSTOMER_CREATED", item.id, {})
        return {"id": item.id, "name": item.name}

    @app.post("/api/v1/admin/licenses")
    def license_create(
        value: s.LicenseInput,
        actor=Depends(writer),
        session: Session = Depends(db, scope="function"),
    ):
        customer_record = session.get(Customer, str(value.customer_id))
        if not customer_record or customer_record.archived_at:
            raise HTTPException(404, "Active customer not found")
        if value.kind != "PERPETUAL" and value.expires_at is None:
            raise HTTPException(422, "Expiration required")
        if value.expires_at and value.expires_at <= now():
            raise HTTPException(422, "Expiration must be in the future")
        item = License(
            **value.model_dump(exclude={"customer_id"}), customer_id=str(value.customer_id)
        )
        session.add(item)
        session.flush()
        audit(session, actor.name, "LICENSE_CREATED", item.id, {})
        return {"id": item.id, "status": item.status}

    def customer_summary(item):
        return {"id": item.id, "name": item.name, "contact_name": item.contact_name,
                "email": item.email, "phone": item.phone, "email_verified": item.email_verified,
                "archived_at": item.archived_at}

    def active_customer(session, ident):
        item = session.get(Customer, str(ident))
        if not item or item.archived_at:
            raise HTTPException(409, "Active customer required")
        return item

    def editable_device(session, ident):
        item = get_device(session, ident)
        if item.archived_at:
            raise HTTPException(409, "Restore archived device before management")
        return item

    @app.patch("/api/v1/admin/customers/{customer_id}")
    def customer_update(customer_id: str, value: s.CustomerUpdate, actor=Depends(writer),
                        session: Session = Depends(db, scope="function")):
        item = active_customer(session, customer_id)
        changes = value.model_dump(exclude={"reason"})
        if item.email != changes["email"]:
            item.email_verified = False
        for key, val in changes.items():
            setattr(item, key, val)
        audit(session, actor.name, "CUSTOMER_UPDATED", item.id, {"reason": value.reason})
        return customer_summary(item)

    @app.post("/api/v1/admin/customers/{customer_id}/{action}")
    def customer_lifecycle(customer_id: str, action: str, value: s.Reason,
                           actor=Depends(writer), session: Session = Depends(db, scope="function")):
        item = session.get(Customer, customer_id)
        if not item or action not in {"archive", "restore"}:
            raise HTTPException(404, "Customer not found")
        if action == "archive":
            licenses = session.scalars(select(License).where(License.customer_id == item.id))
            if any(l.status == "ACTIVE" and (not l.expires_at or utc(l.expires_at) > now()) for l in licenses):
                raise HTTPException(409, "Suspend or revoke active customer licenses before archival")
            if session.scalar(select(Device.id).where(Device.customer_id == item.id,
                    Device.archived_at.is_(None), Device.status.in_(["ACTIVE", "SUSPENDED"])).limit(1)):
                raise HTTPException(409, "Release active device association before customer archival")
            item.archived_at = item.archived_at or now()
        else:
            item.archived_at = None
        audit(session, actor.name, "CUSTOMER_" + action.upper(), item.id, value.model_dump())
        return customer_summary(item)

    @app.post("/api/v1/admin/devices")
    def device_create(value: s.DeviceCreate, actor=Depends(writer),
                      session: Session = Depends(db, scope="function")):
        if session.scalar(select(Device).where(Device.serial == value.serial)):
            raise HTTPException(409, "Hardware serial already registered; inspect existing record")
        if value.customer_id:
            active_customer(session, value.customer_id)
        item = Device(serial=value.serial, model=value.model, firmware="not-enrolled",
                      display_name=value.display_name, notes=value.notes,
                      customer_id=str(value.customer_id) if value.customer_id else None, status="PENDING")
        session.add(item)
        session.flush()
        audit(session, actor.name, "DEVICE_CREATED", item.id, {"serial": item.serial})
        return summary(session, item)

    @app.patch("/api/v1/admin/devices/{device_id}")
    def device_update(device_id: str, value: s.DeviceUpdate, actor=Depends(writer),
                      session: Session = Depends(db, scope="function")):
        item = editable_device(session, device_id)
        lic = license_for(session, item)
        customer_id = str(value.customer_id) if value.customer_id else None
        if lic and customer_id != lic.customer_id:
            raise HTTPException(409, "Use controlled reassignment to change licensed device ownership")
        if customer_id:
            active_customer(session, customer_id)
        item.display_name, item.notes, item.customer_id = value.display_name, value.notes, customer_id
        audit(session, actor.name, "DEVICE_UPDATED", item.id, {"reason": value.reason})
        return summary(session, item)

    @app.post("/api/v1/admin/devices/{device_id}/archive")
    def device_archive(device_id: str, value: s.Reason, actor=Depends(writer),
                       session: Session = Depends(db, scope="function")):
        item = get_device(session, device_id)
        if state(session, item) == "ACTIVE":
            raise HTTPException(409, "Revoke or suspend active device before archival")
        item.archived_at, item.status = item.archived_at or now(), "REVOKED"
        for token in session.scalars(select(ActivationToken).where(
                ActivationToken.device_id == item.id, ActivationToken.used_at.is_(None))):
            token.expires_at = now()
        audit(session, actor.name, "DEVICE_ARCHIVE", item.id, value.model_dump())
        return summary(session, item)

    @app.post("/api/v1/admin/devices/{device_id}/restore")
    def device_restore(device_id: str, value: s.Reason, actor=Depends(writer),
                       session: Session = Depends(db, scope="function")):
        item = get_device(session, device_id)
        item.archived_at = None
        audit(session, actor.name, "DEVICE_RESTORE", item.id, value.model_dump())
        return summary(session, item)

    def license_summary(session, lic):
        customer = session.get(Customer, lic.customer_id)
        bindings = list(
            session.scalars(select(LicenseBinding).where(LicenseBinding.license_id == lic.id))
        )
        status = lic.status
        if status == "ACTIVE" and lic.expires_at and utc(lic.expires_at) <= now():
            status = "EXPIRED"
        return {
            "id": lic.id,
            "customer_id": lic.customer_id,
            "customer_name": customer.name if customer else None,
            "kind": lic.kind,
            "status": status,
            "issued_at": lic.issued_at,
            "expires_at": lic.expires_at,
            "max_devices": lic.max_devices,
            "last_validated_at": lic.last_validated_at,
            "device_ids": [b.device_id for b in bindings],
            "used_devices": len(bindings),
        }

    @app.get("/api/v1/admin/session")
    def administrator_session(actor=Depends(admin)):
        return {"name": actor.name, "role": actor.role, "expires_at": actor.expires_at}

    @app.get("/api/v1/admin/customers")
    def customer_list(
        offset: int = 0,
        limit: int = 200,
        include_archived: bool = False,
        actor=Depends(admin),
        session: Session = Depends(db, scope="function"),
    ):
        if offset < 0 or not 1 <= limit <= 200:
            raise HTTPException(422, "Invalid pagination")
        return [
            customer_summary(c)
            for c in session.scalars(
                select(Customer).where(True if include_archived else Customer.archived_at.is_(None))
                .order_by(Customer.name, Customer.id).offset(offset).limit(limit)
            )
        ]

    @app.get("/api/v1/admin/licenses")
    def license_list(
        offset: int = 0,
        limit: int = 200,
        actor=Depends(admin),
        session: Session = Depends(db, scope="function"),
    ):
        if offset < 0 or not 1 <= limit <= 200:
            raise HTTPException(422, "Invalid pagination")
        return [
            license_summary(session, lic)
            for lic in session.scalars(
                select(License)
                .order_by(License.issued_at.desc(), License.id)
                .offset(offset)
                .limit(limit)
            )
        ]

    @app.get("/api/v1/admin/events")
    def event_list(
        offset: int = 0,
        limit: int = 100,
        actor=Depends(admin),
        session: Session = Depends(db, scope="function"),
    ):
        if offset < 0 or not 1 <= limit <= 200:
            raise HTTPException(422, "Invalid pagination")
        return [
            {
                "id": e.id,
                "actor": e.actor,
                "action": e.action,
                "target": e.target,
                "detail": e.detail,
                "created_at": e.created_at,
            }
            for e in session.scalars(
                select(AuditLog)
                .order_by(AuditLog.created_at.desc(), AuditLog.id)
                .offset(offset)
                .limit(limit)
            )
        ]

    def summary(session, device):
        lic = license_for(session, device)
        customer = session.get(Customer, device.customer_id) if device.customer_id else None
        recovery = session.scalar(select(AuditLog).where(
            AuditLog.target == device.id, AuditLog.action == "REASSIGNED_RELEASED"
        ).order_by(AuditLog.created_at.desc()))
        pending_ids = [
            i.id
            for i in session.scalars(
                select(Installation).where(
                    Installation.device_id == device.id, Installation.current.is_(False)
                )
            )
            if (not recovery or utc(i.created_at) >= utc(recovery.created_at))
            and not session.scalar(
                select(ActivationToken.id)
                .where(
                    ActivationToken.installation_id == i.id, ActivationToken.used_at.is_not(None)
                )
                .limit(1)
            )
        ]
        return {
            "id": device.id,
            "serial": device.serial,
            "model": device.model,
            "firmware": device.firmware,
            "display_name": device.display_name, "notes": device.notes,
            "archived_at": device.archived_at,
            "status": state(session, device),
            "customer_id": device.customer_id,
            "license_id": lic.id if lic else None,
            "last_seen": device.last_seen,
            "ssid": "infrabox-" + device.serial[-8:],
            "pending_installations": pending_ids,
            "customer": {"id": customer.id, "name": customer.name} if customer else None,
            "license": license_summary(session, lic) if lic else None,
        }

    @app.get("/api/v1/admin/devices")
    def devices(
        offset: int = 0,
        limit: int = 100,
        include_archived: bool = False,
        actor=Depends(admin),
        session: Session = Depends(db, scope="function"),
    ):
        if offset < 0 or not 1 <= limit <= 200:
            raise HTTPException(422, "Invalid pagination")
        return [
            summary(session, d)
            for d in session.scalars(
                select(Device).where(True if include_archived else Device.archived_at.is_(None))
                .order_by(Device.created_at, Device.id).offset(offset).limit(limit)
            )
        ]

    @app.get("/api/v1/admin/devices/{device_id}")
    def device_detail(
        device_id: str, actor=Depends(admin), session: Session = Depends(db, scope="function")
    ):
        device = get_device(session, device_id)
        result = summary(session, device)
        last_proof = session.scalar(select(RegistrationEvent).where(
            RegistrationEvent.device_id == device.id, RegistrationEvent.kind == "AUTHENTICATED"
        ).order_by(RegistrationEvent.created_at.desc()))
        result["approval_identity"] = None
        if last_proof:
            observed = session.get(Installation, last_proof.detail.get("installation_id"))
            if observed and observed.device_id == device.id:
                keys = list(session.scalars(select(DeviceKey).where(DeviceKey.installation_id == observed.id)))
                if len(keys) == 1:
                    result["approval_identity"] = {"installation_id": observed.id, "public_key": keys[0].public_key}
        result["installations"] = [
            {
                "id": i.id,
                "current": i.current,
                "keys": [
                    {"public_key": k.public_key, "current": k.current}
                    for k in session.scalars(
                        select(DeviceKey).where(DeviceKey.installation_id == i.id)
                    )
                ],
            }
            for i in session.scalars(
                select(Installation).where(Installation.device_id == device.id)
            )
        ]
        result["events"] = [
            {"kind": e.kind, "detail": e.detail, "created_at": e.created_at}
            for e in session.scalars(
                select(RegistrationEvent)
                .where(RegistrationEvent.device_id == device.id)
                .order_by(RegistrationEvent.created_at.desc())
                .limit(100)
            )
        ]
        return result

    @app.post("/api/v1/admin/devices/{device_id}/approve")
    def approve(
        device_id: str,
        value: s.Approval,
        actor=Depends(writer),
        session: Session = Depends(db, scope="function"),
    ):
        device = editable_device(session, device_id)
        if device.status in {"REVOKED", "SUSPENDED"}:
            raise HTTPException(409, "Explicit reassignment required")
        inst = session.get(Installation, str(value.installation_id))
        key = session.scalar(select(DeviceKey).where(DeviceKey.public_key == value.public_key))
        lic = session.get(License, str(value.license_id))
        if (
            not inst
            or inst.device_id != device.id
            or not key
            or key.installation_id != inst.id
            or not lic
        ):
            raise HTTPException(422, "Invalid approval binding")
        current = session.scalar(
            select(Installation).where(
                Installation.device_id == device.id, Installation.current.is_(True)
            )
        )
        if current and current.id != inst.id:
            raise HTTPException(409, "Explicit recovery/reassignment required")
        if session.scalar(
            select(DeviceKey).where(
                DeviceKey.installation_id == inst.id,
                DeviceKey.current.is_(True),
                DeviceKey.id != key.id,
            )
        ):
            raise HTTPException(409, "Explicit key reassignment required")
        active_customer(session, lic.customer_id)
        if lic.status != "ACTIVE" or (lic.expires_at and utc(lic.expires_at) <= now()):
            raise HTTPException(409, "License unavailable")
        if value.automatic_activation:
            binding = session.get(LicenseBinding, device.id)
            if binding and binding.license_id != lic.id:
                raise HTTPException(409, "Explicit license reassignment required")
            used = session.scalar(select(func.count()).select_from(LicenseBinding)
                                  .where(LicenseBinding.license_id == lic.id))
            if not binding and used >= lic.max_devices:
                raise HTTPException(409, "License capacity reached; select another license")
        # A new administrator decision replaces unconsumed approvals for this device.
        for previous in session.scalars(select(ActivationToken).where(
                ActivationToken.device_id == device.id,
                ActivationToken.used_at.is_(None), ActivationToken.expires_at > now())):
            previous.expires_at = now()
        token = secrets.token_urlsafe(32)
        session.add(
            ActivationToken(
                token_hash=digest(token),
                device_id=device.id,
                installation_id=inst.id,
                key_id=key.id,
                license_id=lic.id,
                expires_at=now() + timedelta(seconds=value.token_ttl_seconds),
                automatic_activation=value.automatic_activation,
            )
        )
        if device.status != "ACTIVE":
            device.status = "ACTIVATION_REQUIRED"
        audit(
            session,
            actor.name,
            "APPROVED",
            device.id,
            {"reason": value.reason, "installation_id": inst.id, "license_id": lic.id,
             "automatic_activation": value.automatic_activation},
        )
        if value.automatic_activation:
            return {"status": "ACTIVATION_REQUIRED", "automatic_activation": True,
                    "expires_in": value.token_ttl_seconds}
        return {"activation_token": token, "expires_in": value.token_ttl_seconds}

    @app.post("/api/v1/admin/devices/{device_id}/suspend")
    def suspend(
        device_id: str,
        value: s.Reason,
        actor=Depends(writer),
        session: Session = Depends(db, scope="function"),
    ):
        device = editable_device(session, device_id)
        device.status = "SUSPENDED"
        audit(session, actor.name, "SUSPENDED", device.id, value.model_dump())
        return {"status": device.status}

    @app.post("/api/v1/admin/devices/{device_id}/revoke")
    def revoke(
        device_id: str,
        value: s.Reason,
        actor=Depends(writer),
        session: Session = Depends(db, scope="function"),
    ):
        device = editable_device(session, device_id)
        device.status = "REVOKED"
        audit(session, actor.name, "REVOKED", device.id, value.model_dump())
        return {"status": device.status}

    @app.post("/api/v1/admin/devices/{device_id}/reassign")
    def reassign(
        device_id: str,
        value: s.Reason,
        actor=Depends(writer),
        session: Session = Depends(db, scope="function"),
    ):
        # Release identity/license; approval then chooses an enrolled replacement.
        # Hardware serial is immutable; other hardware requires a separate device record.
        device = editable_device(session, device_id)
        for inst in session.scalars(
            select(Installation).where(Installation.device_id == device.id)
        ):
            inst.current = False
            for key in session.scalars(
                select(DeviceKey).where(DeviceKey.installation_id == inst.id)
            ):
                key.current = False
        for token in session.scalars(
            select(ActivationToken).where(
                ActivationToken.device_id == device.id, ActivationToken.used_at.is_(None)
            )
        ):
            token.expires_at = now()
        binding = session.get(LicenseBinding, device.id)
        if binding:
            session.delete(binding)
        device.status = "PENDING"
        device.customer_id = None
        audit(session, actor.name, "REASSIGNED_RELEASED", device.id, value.model_dump())
        return {"status": device.status, "next": "Approve replacement installation explicitly"}

    @app.post("/api/v1/admin/licenses/{license_id}/renew")
    def renew(
        license_id: str,
        value: s.Renewal,
        actor=Depends(writer),
        session: Session = Depends(db, scope="function"),
    ):
        lic = session.get(License, license_id)
        if not lic:
            raise HTTPException(404, "License not found")
        active_customer(session, lic.customer_id)
        if lic.status == "REVOKED" or value.expires_at <= now():
            raise HTTPException(409, "Cannot renew revoked license or use a past expiration")
        lic.expires_at = value.expires_at
        audit(
            session,
            actor.name,
            "LICENSE_RENEWED",
            lic.id,
            {"reason": value.reason, "expires_at": value.expires_at.isoformat()},
        )
        return {"id": lic.id, "expires_at": lic.expires_at}

    @app.post("/api/v1/admin/licenses/{license_id}/{action}")
    def license_control(
        license_id: str,
        action: str,
        value: s.Reason,
        actor=Depends(writer),
        session: Session = Depends(db, scope="function"),
    ):
        lic = session.get(License, license_id)
        if not lic or action not in {"suspend", "revoke", "resume"}:
            raise HTTPException(404, "Not found")
        if lic.status == "REVOKED":
            raise HTTPException(409, "Issue a new license after revocation")
        if action == "resume":
            active_customer(session, lic.customer_id)
        lic.status = {"suspend": "SUSPENDED", "revoke": "REVOKED", "resume": "ACTIVE"}[action]
        audit(session, actor.name, "LICENSE_" + action.upper(), lic.id, value.model_dump())
        return {"id": lic.id, "status": lic.status}

    return app


app = create_app()
