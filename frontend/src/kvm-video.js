/* Decode complete JPEG frames before replacing the displayed KVM image. */
(() => {
  const MAX_FRAME_BYTES = 8 * 1024 * 1024;

  class JPEGFrames {
    constructor() { this.pending = new Uint8Array(); }
    push(chunk) {
      if (this.pending.length + chunk.length > MAX_FRAME_BYTES) throw new Error("Video frame exceeds limit");
      const data = new Uint8Array(this.pending.length + chunk.length);
      data.set(this.pending); data.set(chunk, this.pending.length);
      const frames = [];
      let offset = 0;
      while (offset < data.length) {
        let start = -1;
        for (let i = offset; i + 1 < data.length; i++) {
          if (data[i] === 255 && data[i + 1] === 216) { start = i; break; }
        }
        if (start < 0) {
          this.pending = data.slice(-1); // A marker may straddle network chunks.
          return frames;
        }
        let end = -1;
        for (let i = start + 2; i + 1 < data.length; i++) {
          if (data[i] === 255 && data[i + 1] === 217) { end = i + 2; break; }
        }
        if (end < 0) {
          this.pending = data.slice(start);
          return frames;
        }
        frames.push(data.slice(start, end));
        offset = end;
      }
      this.pending = new Uint8Array();
      return frames;
    }
  }

  class CompleteVideoStream {
    constructor(image) {
      this.image = image;
      this.generation = 0;
      this.controller = null;
      this.currentURL = null;
    }
    stop() {
      this.generation++;
      this.controller?.abort();
      this.controller = null;
    }
    dispose() {
      this.stop();
      this.image.removeAttribute("src");
      if (this.currentURL) URL.revokeObjectURL(this.currentURL);
      this.currentURL = null;
    }
    async present(frame, generation) {
      const url = URL.createObjectURL(new Blob([frame], { type: "image/jpeg" }));
      try {
        const decoded = new Image();
        decoded.src = url;
        await decoded.decode();
        if (generation !== this.generation) return;
        const previous = this.currentURL;
        this.image.src = url;
        this.currentURL = url;
        if (previous) URL.revokeObjectURL(previous);
      } finally {
        if (url !== this.currentURL) URL.revokeObjectURL(url);
      }
    }
    async start(url, onError) {
      this.stop();
      const generation = this.generation;
      const controller = new AbortController();
      this.controller = controller;
      let reader;
      try {
        const response = await fetch(url, { cache: "no-store", signal: controller.signal });
        if (!response.ok || !response.body) throw new Error(`Video stream HTTP ${response.status}`);
        reader = response.body.getReader();
        const parser = new JPEGFrames();
        while (generation === this.generation) {
          const { value, done } = await reader.read();
          if (done) throw new Error("Video stream ended");
          const frames = parser.push(value);
          // If rendering falls behind, paint the newest complete frame.
          if (frames.length) await this.present(frames[frames.length - 1], generation);
        }
      } catch (error) {
        if (generation === this.generation && error.name !== "AbortError") onError(error);
      } finally {
        await reader?.cancel().catch(() => {});
        if (this.controller === controller) this.controller = null;
      }
    }
  }

  if (typeof module !== "undefined" && module.exports) module.exports = { JPEGFrames, CompleteVideoStream };
  else window.InfraBoxVideo = { JPEGFrames, CompleteVideoStream };
})();
