"use client";

import { useEffect, useRef } from "react";

interface AudioVisualizerProps {
    isActive: boolean;
}

export function AudioVisualizer({ isActive }: AudioVisualizerProps) {
    const canvasRef = useRef<HTMLCanvasElement>(null);

    useEffect(() => {
        if (!isActive) return;

        const canvas = canvasRef.current;
        if (!canvas) return;

        const ctx = canvas.getContext("2d");
        if (!ctx) return;

        let animationId: number;

        const draw = () => {
            const width = canvas.width;
            const height = canvas.height;

            ctx.clearRect(0, 0, width, height);

            // Mock visualization for demo if no direct analyser attached here
            // (In a real app, we'd pass the AnalyserNode in props)
            const time = Date.now() / 1000;
            const bars = 20;
            const barWidth = width / bars;

            for (let i = 0; i < bars; i++) {
                const heightScale = Math.sin(i * 0.5 + time * 5) * 0.5 + 0.5;
                const barHeight = heightScale * (height * 0.8);

                const x = i * barWidth;
                const y = (height - barHeight) / 2;

                ctx.fillStyle = `rgba(99, 102, 241, ${0.5 + heightScale * 0.5})`; // Indigo-500
                ctx.fillRect(x + 2, y, barWidth - 4, barHeight);
            }

            animationId = requestAnimationFrame(draw);
        };

        draw();

        return () => {
            cancelAnimationFrame(animationId);
            ctx.clearRect(0, 0, canvas.width, canvas.height);
        };
    }, [isActive]);

    return (
        <canvas
            ref={canvasRef}
            width={300}
            height={100}
            className="w-full h-32 rounded-lg bg-black/5"
        />
    );
}
