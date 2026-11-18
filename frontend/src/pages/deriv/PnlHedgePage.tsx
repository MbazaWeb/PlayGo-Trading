import React from 'react';
import { Download } from 'lucide-react';
import DerivMarketPanel from '../../DerivMarketPanel';
import { Account, NotificationLog, Snapshot } from '../../types/trading';

type Props = {
  load: (path: string) => Promise<unknown>;
  data: Snapshot | null;
  selected: Account | undefined;
  logs: NotificationLog[];
};

export default function PnlHedgePage({ load, data, selected, logs }: Props) {
  function exportCsvReport() {
    const headers = ['Timestamp', 'Category', 'Title', 'Amount', 'Details'];
    const rows = logs.map((item) => [
      new Date(item.time).toISOString(),
      item.category.toUpperCase(),
      `"${item.title.replace(/"/g, '""')}"`,
      item.amountLabel || '',
      `"${item.message.replace(/"/g, '""')}"`,
    ]);

    const csvContent = [headers.join(','), ...rows.map((r) => r.join(','))].join('\n');
    const blob = new Blob([csvContent], { type: 'text/csv;charset=utf-8;' });
    const url = URL.createObjectURL(blob);
    const link = document.createElement('a');
    link.href = url;
    link.setAttribute(
      'download',
      `playgo-pnl-report-${selected?.account_id || 'deriv'}-${new Date().toISOString().slice(0, 10)}.csv`
    );
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
    URL.revokeObjectURL(url);
  }

  return (
    <div className="independentPage">
      <div className="pnlTopBar">
        <small>Export recorded P&amp;L and activity alerts for accounting</small>
        <button type="button" className="exportCsvBtn" onClick={exportCsvReport} disabled={logs.length === 0}>
          <Download size={14} /> Export Activity &amp; P&amp;L CSV ({logs.length})
        </button>
      </div>
      <DerivMarketPanel
        view="performance"
        load={load}
        accountId={data?.connected ? selected?.account_id : undefined}
        accountType={selected?.account_type}
      />
    </div>
  );
}
