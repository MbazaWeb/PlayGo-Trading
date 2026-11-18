import React from 'react';
import DerivMarketPanel from '../../DerivMarketPanel';
import { Account, Snapshot } from '../../types/trading';

type Props = {
  load: (path: string) => Promise<unknown>;
  data: Snapshot | null;
  selected: Account | undefined;
};

export default function PnlHedgePage({ load, data, selected }: Props) {
  return (
    <div className="independentPage">
      <DerivMarketPanel
        key={selected?.account_id}
        view="performance"
        load={load}
        accountId={data?.connected ? selected?.account_id : undefined}
        accountType={selected?.account_type}
        accountBalance={selected?.balance}
      />
    </div>
  );
}
