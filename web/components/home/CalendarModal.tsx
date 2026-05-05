"use client";

import React from "react";
import { X } from "lucide-react";

interface CalendarModalProps {
  monthId: number;
  onClose: () => void;
}

export default function CalendarModal({ monthId, onClose }: CalendarModalProps) {
  // Simplified Calendar Grid logic
  const days = ["一", "二", "三", "四", "五", "六", "日"];
  const dates = Array.from({ length: 35 }, (_, i) => i - 1); // Mock 4월

  return (
    <div className="fixed inset-0 z-[100] flex items-center justify-center p-6">
      {/* Backdrop */}
      <div 
        className="absolute inset-0 bg-dark/60 backdrop-blur-md transition-opacity"
        onClick={onClose}
      />
      
      {/* Modal Content */}
      <div className="relative bg-white w-full max-w-sm rounded-[40px] shadow-2xl overflow-hidden animate-in fade-in zoom-in duration-300">
        <div className="p-8 pb-4 flex justify-between items-center bg-soft">
          <div>
            <h2 className="text-2xl font-bold">2026 赛事日历</h2>
            <p className="text-sm font-medium text-dark/40 uppercase tracking-widest">
              April | 4月
            </p>
          </div>
          <button 
            onClick={onClose}
            className="w-10 h-10 rounded-full bg-white flex items-center justify-center text-dark shadow-sm active:scale-95 transition-transform"
          >
            <X size={20} />
          </button>
        </div>

        <div className="p-8">
          {/* Days Header */}
          <div className="grid grid-cols-7 mb-4 text-center">
            {days.map(day => (
              <span key={day} className="text-xs font-bold text-dark/30 uppercase">
                {day}
              </span>
            ))}
          </div>

          {/* Dates Grid */}
          <div className="grid grid-cols-7 gap-y-4 text-center">
            {dates.map((date, i) => {
              const isEmpty = date < 1 || date > 30;
              const isToday = date === 13;
              
              return (
                <div key={i} className="relative h-10 flex items-center justify-center">
                  <span className={`text-sm font-bold ${isEmpty ? 'text-dark/5' : isToday ? 'text-white' : 'text-dark'}`}>
                    {date > 0 && date <= 30 ? date : date <= 0 ? 31 + date : date - 30}
                  </span>
                  {isToday && (
                    <div className="absolute inset-0 m-1 bg-dark rounded-xl -z-10" />
                  )}
                  
                  {/* Mock Event Bar */}
                  {date >= 10 && date <= 15 && (
                    <div className="absolute bottom-0 left-0 right-0 h-1 bg-mint rounded-full mx-1 translate-y-2" />
                  )}
                </div>
              );
            })}
          </div>

          {/* Event Legend */}
          <div className="mt-8 space-y-3">
            <div className="flex items-center gap-3 p-4 bg-soft rounded-2xl">
              <div className="w-1.5 h-8 bg-mint rounded-full" />
              <div>
                <p className="text-xs font-bold text-dark/40 uppercase tracking-tighter">10 - 15 APR</p>
                <p className="text-sm font-bold">WTT 冠军赛重庆站</p>
              </div>
            </div>
          </div>
        </div>

        <div className="p-8 pt-0">
          <button 
            onClick={onClose}
            className="w-full h-14 bg-dark text-white rounded-2xl font-bold hover:bg-dark/90 transition-colors"
          >
            Close Calendar
          </button>
        </div>
      </div>
    </div>
  );
}
