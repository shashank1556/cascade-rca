import React from 'react';
import { Clock, ShieldAlert, ArrowDown } from 'lucide-react';
import type { TimelineEvent } from '../api';

export interface TimelineProps {
  timeline: TimelineEvent[];
  rootCauseService: string | null;
  independentServices?: string[];
}

export const Timeline: React.FC<TimelineProps> = ({
  timeline,
  rootCauseService,
  independentServices = [],
}) => {
  if (!timeline || timeline.length === 0) {
    return (
      <div className="timeline-card card">
        <div className="card-header-bar">
          <div className="flex items-center gap-2">
            <Clock className="w-5 h-5 text-indigo-400" />
            <h3 className="text-base font-bold text-white">Propagation Timeline</h3>
          </div>
        </div>
        <p className="p-4 text-sm text-slate-400 italic text-center">
          No timeline events recorded. Inject a scenario to view real-time temporal onset and
          cascade progression.
        </p>
      </div>
    );
  }

  // Safe timestamp handling conforming to instructions
  const formatTime = (ts: string): string => {
    const date = new Date(ts);
    if (Number.isNaN(date.getTime())) {
      return ts;
    }
    return date.toLocaleTimeString([], {
      hour: '2-digit',
      minute: '2-digit',
      second: '2-digit',
      fractionalSecondDigits: 3,
    });
  };

  const getEventBadgeClass = (service: string) => {
    if (service === rootCauseService) {
      return 'badge-root';
    }
    if (independentServices.includes(service)) {
      return 'badge-independent';
    }
    return 'badge-cascaded';
  };

  return (
    <div className="timeline-card card">
      <div className="card-header-bar">
        <div className="flex items-center gap-2">
          <Clock className="w-5 h-5 text-indigo-400" />
          <h3 className="text-base font-bold text-white">Propagation Timeline</h3>
        </div>
        <span className="text-xs font-mono text-slate-400">
          {timeline.length} Events Logged
        </span>
      </div>

      <div className="timeline-stream-container">
        <div className="timeline-line"></div>
        {timeline.map((item, index) => {
          const badgeClass = getEventBadgeClass(item.service);
          const isRoot = item.service === rootCauseService;

          return (
            <div key={`${item.timestamp}-${item.service}-${index}`} className="timeline-item">
              {/* Node dot on timeline track */}
              <div className={`timeline-dot ${badgeClass}`}>
                {isRoot ? (
                  <ShieldAlert className="w-3.5 h-3.5 text-white" />
                ) : (
                  <ArrowDown className="w-3.5 h-3.5 text-slate-300" />
                )}
              </div>

              {/* Event Content Box */}
              <div className="timeline-content">
                <div className="timeline-meta-row">
                  <span className={`service-name-badge ${badgeClass}`}>{item.service}</span>
                  <span className="timestamp font-mono">{formatTime(item.timestamp)}</span>
                </div>
                <p className="event-description">{item.event}</p>
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
};
