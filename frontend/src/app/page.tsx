"use client";

import { useState, useEffect, useRef, useCallback } from 'react';
import { AudioLoop } from '@/lib/audio_loop';
import { AudioPlayer } from '@/lib/audio_player';
import { AudioVisualizer } from '@/components/AudioVisualizer';
import { Mic, MicOff, Activity, Clock, Settings, User } from 'lucide-react';
import clsx from 'clsx';

export default function Home() {
  const [isConnected, setIsConnected] = useState(false);
  const [isRecording, setIsRecording] = useState(false);
  const [status, setStatus] = useState("Disconnected");
  const [isRinging, setIsRinging] = useState(false);

  const [alarms, setAlarms] = useState<any[]>([]);
  const [timers, setTimers] = useState<any[]>([]);
  const [profile, setProfile] = useState<any>({});

  const fetchProfile = async () => {
    try {
      const res = await fetch("http://localhost:8000/profile");
      const data = await res.json();
      console.log("DEBUG: Profile Data:", data); // Add Log
      setProfile(data);
    } catch (e) {
      console.error("Failed to fetch profile", e);
    }
  };

  const fetchAlarms = async () => {
    try {
      const res = await fetch("http://localhost:8000/alarms");
      const data = await res.json();
      setAlarms(data);
    } catch (e) {
      console.error("Failed to fetch alarms", e);
    }
  };

  const fetchTimers = async () => {
    try {
      const res = await fetch("http://localhost:8000/timers");
      const data = await res.json();
      setTimers(data);
    } catch (e) {
      console.error("Failed to fetch timers", e);
    }
  };

  useEffect(() => {
    fetchAlarms();
    fetchTimers();
    fetchProfile();
    // Poll every 5 seconds for updates
    const interval = setInterval(() => {
      fetchAlarms();
      fetchTimers();
      fetchProfile();
    }, 5000);
    return () => clearInterval(interval);
  }, []);

  const websocketRef = useRef<WebSocket | null>(null);
  const audioLoopRef = useRef<AudioLoop | null>(null);
  const audioPlayerRef = useRef<AudioPlayer | null>(null);
  const alarmAudioRef = useRef<HTMLAudioElement | null>(null);

  // Initialize alarm audio
  useEffect(() => {
    alarmAudioRef.current = new Audio('https://codeskulptor-demos.commondatastorage.googleapis.com/pang/arrow.mp3'); // Better loopable sound?
    // Or use the pop sound but loop it manually or use a longer file. 
    // Let's stick to a simple one for now but set loop = true
    alarmAudioRef.current.loop = true;
  }, []);

  const stopAlarm = () => {
    if (alarmAudioRef.current) {
      alarmAudioRef.current.pause();
      alarmAudioRef.current.currentTime = 0;
    }
    setIsRinging(false);
  };

  const connect = useCallback(() => {
    if (websocketRef.current) return;

    const ws = new WebSocket("ws://localhost:8000/ws/audio");
    audioPlayerRef.current = new AudioPlayer(24000);

    ws.onopen = () => {
      setIsConnected(true);
      setStatus("Connected");
    };

    ws.onclose = () => {
      setIsConnected(false);
      setIsRecording(false);
      setStatus("Disconnected");
      websocketRef.current = null;
    };

    ws.onmessage = async (event) => {
      const data = JSON.parse(event.data);

      // Handle Notification
      if (data.type === "notification") {
        setIsRinging(true);
        alarmAudioRef.current?.play().catch(e => console.log("Audio play failed", e));

        // Refresh lists
        fetchAlarms();
        fetchTimers();
        return;
      }

      // Handle Server Content (Audio)
      if (data.serverContent?.modelTurn?.parts) {
        // If the agent starts speaking, stop the alarm!
        stopAlarm();

        for (const part of data.serverContent.modelTurn.parts) {
          if (part.inlineData && part.inlineData.mimeType.startsWith("audio/")) {
            audioPlayerRef.current?.play(part.inlineData.data);
          }
        }
      }
    };

    websocketRef.current = ws;
  }, []);

  const toggleRecording = async () => {
    if (!isRecording) {
      if (!websocketRef.current) connect();

      try {
        const loop = new AudioLoop();
        loop.onAudioData = (base64Data) => {
          if (websocketRef.current && websocketRef.current.readyState === WebSocket.OPEN) {
            websocketRef.current.send(JSON.stringify({ realtime_input: { media_chunks: [{ mime_type: "audio/pcm", data: base64Data }] } }));
          }
        };
        await loop.start();
        audioLoopRef.current = loop;
        setIsRecording(true);
        setStatus("Listening...");
      } catch (e) {
        console.error(e);
        setStatus("Error accessing microphone");
      }
    } else {
      if (audioLoopRef.current) {
        audioLoopRef.current.stop();
        audioLoopRef.current = null;
      }
      setIsRecording(false);
      setStatus("Connected");
    }
  };

  useEffect(() => {
    // Initial connection attempt
    connect();
    return () => {
      if (websocketRef.current) websocketRef.current.close();
      if (audioLoopRef.current) audioLoopRef.current.stop();
    };
  }, [connect]);

  return (
    <main className="flex min-h-screen flex-col items-center justify-between p-24 bg-gradient-to-br from-slate-900 to-slate-800 text-white">

      <div className="z-10 max-w-5xl w-full items-center justify-between font-mono text-sm lg:flex">
        <p className="fixed left-0 top-0 flex w-full justify-center border-b border-gray-300 bg-gradient-to-b from-zinc-200 pb-6 pt-8 backdrop-blur-2xl dark:border-neutral-800 dark:bg-zinc-800/30 dark:from-inherit lg:static lg:w-auto  lg:rounded-xl lg:border lg:bg-gray-200 lg:p-4 lg:dark:bg-zinc-800/30">
          Agentic Voice Assistant
        </p>
        <div className="fixed bottom-0 left-0 flex h-48 w-full items-end justify-center bg-gradient-to-t from-white via-white dark:from-black dark:via-black lg:static lg:h-auto lg:w-auto lg:bg-none">
          <div className="flex items-center gap-2 pointer-events-none p-2 place-items-center lg:pointer-events-auto lg:p-0">
            <Activity className={clsx("w-5 h-5", isConnected ? "text-green-400" : "text-red-400")} />
            <span>{status}</span>
          </div>
        </div>
      </div>

      <div className="flex flex-col items-center gap-8 relative">
        <div className="relative">
          <div className={clsx("absolute -inset-4 bg-indigo-500 rounded-full opacity-20 blur-xl transition-all duration-500", isRecording && "scale-150 opacity-40")}></div>
          <button
            onClick={toggleRecording}
            className={clsx("relative z-10 w-32 h-32 rounded-full flex items-center justify-center transition-all duration-300 shadow-2xl border-4",
              isRecording ? "bg-red-500 border-red-400 hover:bg-red-600" : "bg-indigo-600 border-indigo-400 hover:bg-indigo-700 hover:scale-105"
            )}
          >
            {isRecording ? <MicOff size={48} /> : <Mic size={48} />}
          </button>
        </div>

        <div className="w-[600px]">
          <AudioVisualizer isActive={isRecording} />
        </div>
      </div>

      <div className="mb-32 grid text-center lg:max-w-5xl lg:w-full lg:mb-0 lg:grid-cols-4 lg:text-left gap-4">
        <Card title="Alarms" icon={<Clock className="w-6 h-6 mb-2" />}>
          {alarms.length === 0 ? <div className="text-sm text-gray-400">No active alarms</div> : (
            <ul className="text-sm space-y-2">
              {alarms.map((a: any) => (
                <li key={a.id} className="flex justify-between bg-white/5 p-2 rounded">
                  <span>{new Date(a.time).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}</span>
                  <span className="text-gray-400 text-xs">{a.label}</span>
                </li>
              ))}
            </ul>
          )}
        </Card>

        <Card title="Timers" icon={<Clock className="w-6 h-6 mb-2" />}>
          {timers.length === 0 ? <div className="text-sm text-gray-400">No active timers</div> : (
            <ul className="text-sm space-y-2">
              {timers.map((t: any) => (
                <li key={t.id} className="flex justify-between bg-white/5 p-2 rounded">
                  <span>{t.label}</span>
                  <span className="text-green-400 text-xs">{(new Date(t.end_time).getTime() - new Date().getTime()) > 0 ? Math.ceil((new Date(t.end_time).getTime() - new Date().getTime()) / 1000) + 's' : 'Done'}</span>
                </li>
              ))}
            </ul>
          )}
        </Card>

        <Card title="Memory" icon={<User className="w-6 h-6 mb-2" />}>
          <div className="text-sm space-y-2">
            {Object.entries(profile).map(([key, value]) => {
              if (!value) return null;
              // Capitalize key
              const label = key.charAt(0).toUpperCase() + key.slice(1).replace(/_/g, ' ');
              return (
                <div key={key} className="flex justify-between bg-white/5 p-2 rounded">
                  <span className="text-gray-400">{label}</span>
                  <span className="truncate max-w-[150px] text-right" title={String(value)}>{String(value)}</span>
                </div>
              );
            })}
            {Object.keys(profile).length === 0 && <div className="text-gray-500 text-xs text-center">No info</div>}
          </div>
        </Card>

        <Card title="Debug" icon={<Settings className="w-6 h-6 mb-2" />}>
          <div className="text-xs font-mono text-gray-500 h-24 overflow-y-auto">
            {">"} System Initialized... <br />
            {isConnected ? "> Connected to Backend" : "> Wireless Disconnected"}
          </div>
        </Card>
      </div >
    </main >
  );
}

function Card({ title, icon, children }: { title: string, icon: React.ReactNode, children: React.ReactNode }) {
  return (
    <div className="group rounded-lg border border-transparent px-5 py-4 transition-colors hover:border-gray-300 hover:bg-gray-100 hover:dark:border-neutral-700 hover:dark:bg-neutral-800/30">
      <h2 className={`mb-3 text-2xl font-semibold flex flex-col items-start`}>
        {icon}
        {title}
      </h2>
      {children}
    </div>
  )
}
