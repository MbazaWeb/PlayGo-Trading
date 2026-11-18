import React from 'react';
import { Wallet, RefreshCw, ExternalLink, ArrowDownLeft, ArrowUpRight } from 'lucide-react';
import { Account, Snapshot } from '../../types/trading';

type Props = {
  token: string;
  oauthBusy: boolean;
  busy: boolean;
  signingIn: boolean;
  data: Snapshot | null;
  selected: Account | undefined;
  selectedId: string;
  error: string;
  username: string;
  password: string;
  onSelectId: (id: string) => void;
  onRefresh: () => void;
  onSignInDeriv: () => void;
  onOwnerLogin: (e: React.FormEvent) => void;
  onUsernameChange: (val: string) => void;
  onPasswordChange: (val: string) => void;
};

function balanceLabel(account: Account) {
  if (account.balance === null) return 'Unavailable';
  const value = Number(account.balance);
  if (!Number.isFinite(value)) return 'Unavailable';
  return `${account.currency} ${value.toLocaleString('en-US', {
    minimumFractionDigits: 2,
    maximumFractionDigits: 8,
  })}`;
}

export default function AccountPage({
  token,
  oauthBusy,
  busy,
  signingIn,
  data,
  selected,
  selectedId,
  error,
  username,
  password,
  onSelectId,
  onRefresh,
  onSignInDeriv,
  onOwnerLogin,
  onUsernameChange,
  onPasswordChange,
}: Props) {
  return (
    <div className="independentPage">
      {data?.connected && selected && (
        <label className="derivAccountSelector">
          Selected Deriv account
          <select value={selectedId || selected.account_id} onChange={(e) => onSelectId(e.target.value)}>
            {data.accounts.map((account) => (
              <option value={account.account_id} key={account.account_id}>
                {account.account_type === 'demo' ? 'Demo' : 'Real'} / {account.currency} / {account.account_id}
              </option>
            ))}
          </select>
        </label>
      )}

      <section className="realHero">
        <div>
          <small>YOUR CONNECTED ACCOUNT</small>
          <h1>
            Your Deriv account<span>.</span>
          </h1>
          <p>Choose your demo or real Options account.</p>
        </div>
        {token && (
          <button disabled={busy} onClick={onRefresh}>
            <RefreshCw size={16} />
            {busy ? 'Refreshing...' : 'Refresh'}
          </button>
        )}
      </section>

      {error && (
        <p className="realError" role="alert">
          {error}
        </p>
      )}

      {oauthBusy ? (
        <p role="status" className="realEmpty">
          Completing Deriv sign-in...
        </p>
      ) : !token ? (
        <section className="realLogin">
          <h2>Welcome to PlayGo</h2>
          <p>Sign in with Deriv to view your demo and real accounts.</p>
          <button className="realPrimary derivSignIn" disabled={oauthBusy} onClick={onSignInDeriv}>
            {oauthBusy ? 'Waiting for Deriv...' : 'Sign in with Deriv'}
            <ExternalLink size={16} />
          </button>
          <small className="derivLoginHelp">
            Sign in securely on Deriv, then return here automatically. Your Deriv password stays with Deriv.
          </small>
          <details className="ownerLogin">
            <summary>PlayGo owner sign-in</summary>
            <form onSubmit={onOwnerLogin}>
              <label>
                Username
                <input
                  required
                  autoComplete="username"
                  value={username}
                  onChange={(e) => onUsernameChange(e.target.value)}
                />
              </label>
              <label>
                Password
                <input
                  required
                  type="password"
                  autoComplete="current-password"
                  value={password}
                  onChange={(e) => onPasswordChange(e.target.value)}
                />
              </label>
              <button disabled={signingIn}>{signingIn ? 'Signing in...' : 'Sign in as owner'}</button>
            </form>
          </details>
        </section>
      ) : busy && !data ? (
        <p role="status" className="realEmpty">
          Checking your Deriv connection...
        </p>
      ) : data?.connected && selected ? (
        <>
          <div className="realStatus">
            <span>Connected to Deriv</span>
            <small>{data.observed_at ? 'Last updated ' + new Date(data.observed_at).toLocaleString() : ''}</small>
          </div>
          <section className="realBalances">
            <article className={selected.account_type === 'demo' ? 'demoAccount' : ''}>
              <div>
                <Wallet size={20} />
                <span>
                  {selected.account_type === 'demo'
                    ? 'DEMO ACCOUNT / VIRTUAL FUNDS'
                    : 'REAL ACCOUNT / REAL FUNDS'}
                </span>
              </div>
              <small>{selected.account_id}</small>
              <strong>{balanceLabel(selected)}</strong>
              <span>
                {selected.account_type === 'demo' ? 'Deriv demo balance' : 'Deriv real balance'} / {selected.currency}
              </span>

              {selected.account_type === 'real' && (
                <div className="cashierActions">
                  <a
                    className="cashierBtn deposit"
                    href="https://app.deriv.com/cashier/deposit"
                    target="_blank"
                    rel="noopener noreferrer"
                  >
                    <ArrowDownLeft size={14} /> Deposit <ExternalLink size={12} />
                  </a>
                  <a
                    className="cashierBtn withdraw"
                    href="https://app.deriv.com/cashier/withdrawal"
                    target="_blank"
                    rel="noopener noreferrer"
                  >
                    <ArrowUpRight size={14} /> Withdraw <ExternalLink size={12} />
                  </a>
                </div>
              )}
            </article>
          </section>
        </>
      ) : data?.connected ? (
        <section className="realEmpty">
          <Wallet size={30} />
          <h2>No Options accounts returned</h2>
          <p>
            Deriv returned no demo or real Options accounts for this sign-in. Wallets and MT5 accounts are not included.
          </p>
        </section>
      ) : (
        <section className="realEmpty">
          <div className="realConnectIcon">
            <Wallet size={30} />
          </div>
          <h2>Sign in with Deriv</h2>
          <p>Authorize Deriv to view your accounts and see whether you are using demo or real funds.</p>
          <button className="realPrimary" disabled={oauthBusy} onClick={onSignInDeriv}>
            {oauthBusy ? 'Waiting for Deriv...' : 'Sign in with Deriv'} <ExternalLink size={16} />
          </button>
        </section>
      )}
    </div>
  );
}
