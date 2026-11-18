import React from 'react';
import DerivMarketPanel from '../../DerivMarketPanel';

type Props = {
  load: (path: string) => Promise<unknown>;
};

export default function MarketPage({ load }: Props) {
  return (
    <div className="independentPage">
      <DerivMarketPanel view="markets" load={load} />
    </div>
  );
}
