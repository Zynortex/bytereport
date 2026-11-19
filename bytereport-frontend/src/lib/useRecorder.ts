import { useCallback, useEffect, useRef, useState } from "react";

export type RecorderState = "idle" | "recording" | "denied" | "unsupported";

/** What one take produced: the audio, and how loud the input actually got. */
export interface Take {
  blob: Blob | null;
  peak: number;
}

/**
 * Peak amplitude below which a take is treated as silence.
 *
 * Not a nicety. The transcription model does not return empty text for silence
 * — it HALLUCINATES. A four-second recording of a quiet room came back as
 * "المشاكل", which would have landed in the note looking like the user's own
 * words. An empty-string check cannot catch that; refusing to upload silence
 * can, and it saves the request too.
 *
 * Measured on this machine: an idle microphone peaks around 0.009, and speech
 * peaks around 0.52 — a gap of roughly 55x, so the exact threshold matters far
 * less than sitting inside that band. 0.02 is double a measured noise floor and
 * a twenty-fifth of speech.
 *
 * The threshold errs LOW on purpose. Wrongly refusing a take the user actually
 * spoke breaks the feature; wrongly accepting a quiet one produces text they
 * can see and delete in the preview. Those costs are not symmetric.
 */
export const SILENCE_PEAK = 0.02;

/**
 * Thin wrapper over MediaRecorder.
 *
 * `stop()` RESOLVES WITH THE RECORDING. That is the whole design point. The
 * obvious alternative — stop, then wait for a `blob` state value to appear —
 * cannot work: a callback that polls `blob` closes over the value from the
 * render that created it, and React state is immutable per render, so the poll
 * re-reads the same stale null until it times out. Recording silently produced
 * nothing. The resolver is held in a ref and called from `onstop`, which is the
 * one place that genuinely knows the recording is complete.
 *
 * The tracks are stopped on every exit path, including unmount: a live
 * MediaStream keeps the browser's recording indicator lit and the microphone
 * held open, which is alarming once the user has navigated away.
 */
export function useRecorder() {
  const [state, setState] = useState<RecorderState>("idle");
  const [blob, setBlob] = useState<Blob | null>(null);
  const [seconds, setSeconds] = useState(0);

  const recorderRef = useRef<MediaRecorder | null>(null);
  const analyserRef = useRef<AnalyserNode | null>(null);
  const audioCtxRef = useRef<AudioContext | null>(null);
  // Loudest sample seen during the take. Measured on the live stream rather
  // than decoded from the blob afterwards: it is cheaper, container-agnostic,
  // and it measures what the microphone actually heard.
  const peakRef = useRef(0);
  // How many times the meter actually read the stream. Zero means the analyser
  // never produced data — which happens: in headless Chrome an analyser fed by
  // a synthetic MediaStream reads nothing at all. If that ever happened in a
  // real browser, a peak of 0 would look like silence and every single take
  // would be refused. The gate may fire on evidence of silence, never on the
  // absence of a measurement.
  const meterTicksRef = useRef(0);
  const streamRef = useRef<MediaStream | null>(null);
  const chunksRef = useRef<BlobPart[]>([]);
  const tickRef = useRef<number | null>(null);
  const meterRef = useRef<number | null>(null);
  const resolveRef = useRef<((take: Take) => void) | null>(null);

  const releaseStream = useCallback(() => {
    streamRef.current?.getTracks().forEach((t) => t.stop());
    streamRef.current = null;
    analyserRef.current = null;
    audioCtxRef.current?.close().catch(() => { /* already closed */ });
    audioCtxRef.current = null;
    for (const ref of [tickRef, meterRef]) {
      if (ref.current !== null) {
        window.clearInterval(ref.current);
        ref.current = null;
      }
    }
  }, []);

  useEffect(() => () => {
    // Unmounting mid-recording must not leave a caller awaiting forever.
    resolveRef.current?.({ blob: null, peak: 0 });
    resolveRef.current = null;
    releaseStream();
  }, [releaseStream]);

  const start = useCallback(async () => {
    if (typeof MediaRecorder === "undefined" || !navigator.mediaDevices?.getUserMedia) {
      setState("unsupported");
      return;
    }
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      streamRef.current = stream;
      chunksRef.current = [];

      // Level meter on the live input. See SILENCE_PEAK for why.
      peakRef.current = 0;
      meterTicksRef.current = 0;
      try {
        const ctx = new AudioContext();
        const analyser = ctx.createAnalyser();
        analyser.fftSize = 2048;
        ctx.createMediaStreamSource(stream).connect(analyser);
        audioCtxRef.current = ctx;
        analyserRef.current = analyser;
      } catch {
        // No Web Audio at all: leave the meter unarmed, which the check below
        // reads as "unmeasured" and lets through.
        analyserRef.current = null;
      }

      // Let the browser choose the container. Chrome gives webm/opus, Safari
      // mp4/aac; both are accepted upstream, and forcing a mimeType the browser
      // does not support throws rather than falling back.
      const rec = new MediaRecorder(stream);
      rec.ondataavailable = (e) => { if (e.data.size > 0) chunksRef.current.push(e.data); };
      rec.onstop = () => {
        const recorded = new Blob(chunksRef.current, { type: rec.mimeType || "audio/webm" });
        setBlob(recorded);
        releaseStream();
        setState("idle");
        // An empty recording is a failure, not a zero-byte upload to pay for.
        resolveRef.current?.({
          blob: recorded.size > 0 ? recorded : null,
          // Unmeasured reads as "loud enough" rather than as silence.
          peak: meterTicksRef.current > 0 ? peakRef.current : Number.POSITIVE_INFINITY,
        });
        resolveRef.current = null;
      };
      recorderRef.current = rec;
      rec.start();

      setBlob(null);
      setSeconds(0);
      setState("recording");
      tickRef.current = window.setInterval(() => setSeconds((s) => s + 1), 1000);

      // The meter runs on its own, much faster timer: one 2048-sample read
      // covers about 43ms of a 48kHz stream, so sampling once a second would
      // let whole words fall between ticks and report a quiet room.
      const samples = new Float32Array(2048);
      meterRef.current = window.setInterval(() => {
        const analyser = analyserRef.current;
        if (!analyser) return;
        analyser.getFloatTimeDomainData(samples);
        meterTicksRef.current += 1;
        for (const v of samples) {
          const level = Math.abs(v);
          if (level > peakRef.current) peakRef.current = level;
        }
      }, 100);
    } catch {
      // Permission refused, or no input device. Both leave the user with the
      // textarea, which is why this is a state and not an exception.
      releaseStream();
      setState("denied");
    }
  }, [releaseStream]);

  /** Stops recording and resolves with the audio, or null if there is none. */
  const stop = useCallback((): Promise<Take> => {
    const rec = recorderRef.current;
    if (!rec || rec.state !== "recording") {
      releaseStream();
      setState("idle");
      return Promise.resolve({ blob: null, peak: 0 });
    }
    return new Promise<Take>((resolve) => {
      resolveRef.current = resolve;
      rec.stop();
    });
  }, [releaseStream]);

  const reset = useCallback(() => { setBlob(null); setSeconds(0); }, []);

  return { state, blob, seconds, start, stop, reset };
}
