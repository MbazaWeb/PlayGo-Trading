export type DashboardPage = 'account' | 'market' | 'trade-bot' | 'pnl-hedge';

export const DASHBOARD_PATHS: Record<DashboardPage, string> = {
  account: '/account',
  market: '/market',
  'trade-bot': '/trade-bot',
  'pnl-hedge': '/pnl-hedge',
};

export const PAGE_TITLES: Record<DashboardPage, string> = {
  account: 'Account',
  market: 'Market',
  'trade-bot': 'Trade Bot',
  'pnl-hedge': 'Profit, loss & hedge exposure',
};

export type Account = {
  account_id: string;
  currency: string;
  balance: string | null;
  account_type: 'real' | 'demo';
};

export type Snapshot = {
  connected: boolean;
  reason?: string;
  accounts: Account[];
  observed_at?: string;
};

export type BotConfig = {
  symbol: string;
  contract_type: 'CALL_PUT' | 'CALL' | 'PUT';
  duration_minutes: number;
  stake: string;
  daily_stake_limit: string;
};

export type DemoBotState = {
  execution: 'DEMO_ONLY';
  strategy: string;
  symbol: string;
  contract_type: string;
  duration_minutes: number;
  stake: string;
  daily_stake_limit: string;
  account_id: string;
  running: boolean;
  status: string;
  daily_stake: string;
  active_contract_id: string | null;
  trade_activity?: {
    time: string;
    initiated_at: string;
    symbol: string;
    side: string;
    stake: string;
    status: string;
    contract_id: string | null;
  }[];
  last_trade: {
    contract_id: string;
    side: string;
    stake: string;
    created_at: string;
    status: string;
  } | null;
  last_cycle_at: string | null;
  last_error: string | null;
};

export type NotificationCategory = 'profit' | 'loss' | 'market' | 'bot' | 'risk';

export type NotificationLog = {
  id: string;
  category: NotificationCategory;
  title: string;
  message: string;
  amountLabel?: string; // mfano "+.00" au "-.00"
  time: string;
  read: boolean;
};
