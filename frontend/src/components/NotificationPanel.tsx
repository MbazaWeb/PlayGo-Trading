import React, { useState } from 'react';
import {
  Bell,
  X,
  TrendingUp,
  TrendingDown,
  Globe,
  Bot,
  AlertTriangle,
  Trash2,
  CheckCheck,
} from 'lucide-react';
import { NotificationCategory, NotificationLog } from '../types/trading';

type Props = {
  logs: NotificationLog[];
  onMarkAllRead: () => void;
  onClearAll: () => void;
};

export default function NotificationPanel({ logs, onMarkAllRead, onClearAll }: Props) {
  const [open, setOpen] = useState(false);
  const [filter, setFilter] = useState<'all' | 'pnl' | 'bot' | 'market'>('all');

  const unreadCount = logs.filter((l) => !l.read).length;

  const filteredLogs = logs.filter((item) => {
    if (filter === 'pnl') return item.category === 'profit' || item.category === 'loss';
    if (filter === 'bot') return item.category === 'bot' || item.category === 'risk';
    if (filter === 'market') return item.category === 'market';
    return true;
  });

  function togglePanel() {
    const next = !open;
    setOpen(next);
    if (next && unreadCount > 0) {
      onMarkAllRead();
    }
  }

  function renderIcon(category: NotificationCategory) {
    switch (category) {
      case 'profit':
        return <TrendingUp size={16} />;
      case 'loss':
        return <TrendingDown size={16} />;
      case 'market':
        return <Globe size={16} />;
      case 'risk':
        return <AlertTriangle size={16} />;
      case 'bot':
      default:
        return <Bot size={16} />;
    }
  }

  return (
    <>
      <button
        type="button"
        className="notifTriggerBtn"
        aria-label="Open notifications panel"
        onClick={togglePanel}
      >
        <Bell size={16} />
        {unreadCount > 0 && <span className="notifBadge">{unreadCount > 99 ? '99+' : unreadCount}</span>}
      </button>

      {open && (
        <div className="notifBackdrop" onClick={() => setOpen(false)}>
          <aside
            className="notifDrawer"
            role="dialog"
            aria-modal="true"
            aria-label="Trading notifications and logs"
            onClick={(e) => e.stopPropagation()}
          >
            <div className="notifDrawerHeader">
              <div>
                <h3>Activity &amp; Alerts</h3>
                <small>{logs.length} recorded events</small>
              </div>
              <div className="notifHeaderBtns">
                {logs.length > 0 && (
                  <>
                    <button type="button" title="Mark all read" onClick={onMarkAllRead}>
                      <CheckCheck size={15} />
                    </button>
                    <button type="button" title="Clear all logs" onClick={onClearAll}>
                      <Trash2 size={15} />
                    </button>
                  </>
                )}
                <button type="button" aria-label="Close notifications" onClick={() => setOpen(false)}>
                  <X size={16} />
                </button>
              </div>
            </div>

            <div className="notifFilters">
              <button
                type="button"
                className={filter === 'all' ? 'selected' : ''}
                onClick={() => setFilter('all')}
              >
                All ({logs.length})
              </button>
              <button
                type="button"
                className={filter === 'pnl' ? 'selected' : ''}
                onClick={() => setFilter('pnl')}
              >
                Profit / Loss
              </button>
              <button
                type="button"
                className={filter === 'bot' ? 'selected' : ''}
                onClick={() => setFilter('bot')}
              >
                Bot &amp; Risk
              </button>
              <button
                type="button"
                className={filter === 'market' ? 'selected' : ''}
                onClick={() => setFilter('market')}
              >
                Market
              </button>
            </div>

            <div className="notifList">
              {filteredLogs.length === 0 ? (
                <div className="notifEmpty">
                  <Bell size={26} />
                  <p>No notifications in this category yet.</p>
                  <small>
                    While the dashboard is open, the bell checks for Deriv settlements, Forex market status changes,
                    and bot activity.
                  </small>
                </div>
              ) : (
                filteredLogs.map((item) => (
                  <article key={item.id} className={`notifCard notif-${item.category}`}>
                    <div className="notifCardIcon">{renderIcon(item.category)}</div>
                    <div className="notifCardBody">
                      <div className="notifCardTop">
                        <b>{item.title}</b>
                        {item.amountLabel && (
                          <span className={`notifAmount ${item.category === 'loss' ? 'neg' : 'pos'}`}>
                            {item.amountLabel}
                          </span>
                        )}
                      </div>
                      <p>{item.message}</p>
                      <small>{new Date(item.time).toLocaleString()}</small>
                    </div>
                  </article>
                ))
              )}
            </div>
          </aside>
        </div>
      )}
    </>
  );
}
