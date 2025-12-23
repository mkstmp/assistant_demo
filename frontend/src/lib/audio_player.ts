export class AudioPlayer {
    private context: AudioContext;
    private nextStartTime: number = 0;

    constructor(sampleRate: number = 24000) {
        this.context = new AudioContext({ sampleRate });
    }

    play(base64PCM: string) {
        const pcmData = this.base64ToInt16(base64PCM);
        const float32Data = this.int16ToFloat32(pcmData);

        const buffer = this.context.createBuffer(1, float32Data.length, this.context.sampleRate);
        buffer.getChannelData(0).set(float32Data);

        const source = this.context.createBufferSource();
        source.buffer = buffer;
        source.connect(this.context.destination);

        const currentTime = this.context.currentTime;
        if (this.nextStartTime < currentTime) {
            this.nextStartTime = currentTime;
        }

        source.start(this.nextStartTime);
        this.nextStartTime += buffer.duration;
    }

    private base64ToInt16(base64: string): Int16Array {
        const binaryString = atob(base64);
        const bytes = new Uint8Array(binaryString.length);
        for (let i = 0; i < binaryString.length; i++) {
            bytes[i] = binaryString.charCodeAt(i);
        }
        return new Int16Array(bytes.buffer as ArrayBuffer);
    }

    private int16ToFloat32(input: Int16Array): Float32Array {
        const output = new Float32Array(input.length);
        for (let i = 0; i < input.length; i++) {
            const int = input[i];
            output[i] = int < 0 ? int / 32768 : int / 32767;
        }
        return output;
    }

    stop() {
        if (this.context) {
            this.context.close();
        }
    }
}
