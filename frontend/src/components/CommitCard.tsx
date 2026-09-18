import React from 'react';
import { GitCommit, ExternalLink, User, ShieldCheck } from 'lucide-react';
import type { CommitInfo } from '../api';

export interface CommitCardProps {
  commit: CommitInfo | null;
  rootCauseService: string | null;
}

export const CommitCard: React.FC<CommitCardProps> = ({ commit, rootCauseService }) => {
  if (!commit) {
    return (
      <div className="commit-card card">
        <div className="card-header-bar">
          <div className="flex items-center gap-2">
            <GitCommit className="w-5 h-5 text-indigo-400" />
            <h3 className="text-base font-bold text-white">GitHub Commit Correlation</h3>
          </div>
        </div>
        <div className="p-4 text-center">
          <p className="text-xs text-slate-400 italic">
            No correlated commit detected for this incident, or GitHub API unavailable.
          </p>
        </div>
      </div>
    );
  }

  return (
    <div className="commit-card card">
      <div className="card-header-bar">
        <div className="flex items-center gap-2">
          <GitCommit className="w-5 h-5 text-indigo-400" />
          <h3 className="text-base font-bold text-white">Correlated GitHub Commit</h3>
        </div>
        <span className="source-tag">Suspicious Recent Change</span>
      </div>

      <div className="commit-body">
        <div className="commit-header-row">
          <div className="flex items-center gap-2">
            <span className="sha-badge font-mono">{commit.sha.substring(0, 7)}</span>
            {rootCauseService && (
              <span className="service-tag font-mono text-xs">{rootCauseService}</span>
            )}
          </div>
          <a
            href={commit.url}
            target="_blank"
            rel="noopener noreferrer"
            className="github-link flex items-center gap-1 text-xs text-indigo-300 hover:text-white"
          >
            <span>View on GitHub</span>
            <ExternalLink className="w-3.5 h-3.5" />
          </a>
        </div>

        <p className="commit-message font-medium text-slate-200 mt-2 text-sm">
          {commit.message}
        </p>

        <div className="commit-meta-footer mt-3 flex items-center justify-between text-xs text-slate-400">
          <div className="flex items-center gap-1.5">
            <User className="w-3.5 h-3.5 text-slate-400" />
            <span>Author: <strong className="text-slate-300">{commit.author}</strong></span>
          </div>
          <div className="flex items-center gap-1 text-emerald-400">
            <ShieldCheck className="w-3.5 h-3.5" />
            <span>Direct correlation detected</span>
          </div>
        </div>
      </div>
    </div>
  );
};
