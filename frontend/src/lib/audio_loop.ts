"use client";

export type AudioConfig = {
    sampleRate: number;
    encoding: "linear16" | "pcm";
};

export class AudioLoop {
    private context: AudioContext | null = null;
    private source: MediaStreamAudioSourceNode | null = null;
    private processor: ScriptProcessorNode | null = null;
    private stream: MediaStream | null = null;
    public onAudioData: ((data: string) => void) | null = null;

    constructor() {}

    async start() {
        try {
            this.stream = await navigator.mediaDevices.getUserMedia({ 
                audio: { 
                    channelCount: 1, 
                    sampleRate: 24000 
                } 
            });
            this.context = new AudioContext({ sampleRate: 24000 });
            this.source = this.context.createMediaStreamSource(this.stream);
            
            // Function to convert Float32 to PCM16 (base64)
            this.processor = this.context.createScriptProcessor(4096, 1, 1);
            
            this.processor.onaudioprocess = (e) => {
                if (!this.onAudioData) return;
                
                const inputData = e.inputBuffer.getChannelData(0);
                const pcmData = this.floatTo16BitPCM(inputData);
                const base64Data = this.arrayBufferToBase64(pcmData);
                
                this.onAudioData(base64Data);
            };

            this.source.connect(this.processor);
            this.processor.connect(this.context.destination);
            
        } catch (error) {
            console.error("Error starting audio loop:", error);
            throw error;
        }
    }

    stop() {
        if (this.processor) {
            this.processor.disconnect();
            this.processor = null;
        }
        if (this.source) {
            this.source.disconnect();
            this.source = null;
        }
        if (this.stream) {
            this.stream.getTracks().forEach(track => track.stop());
            this.stream = null;
        }
        if (this.context) {
            this.context.close();
            this.context = null;
        }
    }

    private floatTo16BitPCM(input: Float32Array): ArrayBuffer {
        const output = new DataView(new ArrayBuffer(input.length * 2));
        for (let i = 0; i < input.length; i++) {
            let s = Math.max(-1, Math.min(1, input[i]));
            // s = s < 0 ? s * 0x8000 : s * 0x7FFF;
            s = s < 0 ? s * 32768 : s * 32767;
            output.setInt16(i * 2, s, true); // little-endian
        }
        return output.buffer;
    }

    private arrayBufferToBase64(buffer: ArrayBuffer): string {
        let binary = '';
        const bytes = new Uint8Array(buffer);
        const len = bytes.byteLength;
        for (let i = 0; i < len; i++) {
            binary += String.fromCharCode(bytes[i]);
        }
        return btoa(binary);
    }
}
