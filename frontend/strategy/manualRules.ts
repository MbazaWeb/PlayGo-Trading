export type ManualStrategyRules = {
  allow_signals: Array<'BUY' | 'SELL'>;
  min_rsi?: number;
  max_rsi?: number;
  max_atr_percent?: number;
};

export type ManualRulesParseResult =
  | { ok: true; rules: ManualStrategyRules }
  | { ok: false; error: string };

export const DEFAULT_MANUAL_RULES: ManualStrategyRules = {
  allow_signals: ['BUY', 'SELL'],
};

export const DEFAULT_MANUAL_RULES_JSON = `{
  "allow_signals": ["BUY", "SELL"],
  "min_rsi": null,
  "max_rsi": null,
  "max_atr_percent": null
}`;

export function parseManualRulesJson(source: string): ManualRulesParseResult {
  let value: unknown;
  try {
    value = JSON.parse(source);
  } catch {
    return { ok: false, error: 'Manual rules must be valid JSON.' };
  }

  if (typeof value !== 'object' || value === null || Array.isArray(value)) {
    return { ok: false, error: 'Manual rules must be a JSON object.' };
  }

  const record = value as Record<string, unknown>;
  const allowedKeys = new Set(['allow_signals', 'min_rsi', 'max_rsi', 'max_atr_percent']);
  const unexpectedKey = Object.keys(record).find((key) => !allowedKeys.has(key));
  if (unexpectedKey) {
    return { ok: false, error: `Unsupported manual rule: ${unexpectedKey}.` };
  }

  const rawSignals = record.allow_signals === undefined
    ? DEFAULT_MANUAL_RULES.allow_signals
    : record.allow_signals;
  if (
    !Array.isArray(rawSignals) ||
    rawSignals.length < 1 ||
    rawSignals.length > 2 ||
    rawSignals.some((signal) => signal !== 'BUY' && signal !== 'SELL') ||
    new Set(rawSignals).size !== rawSignals.length
  ) {
    return { ok: false, error: 'allow_signals must contain BUY, SELL, or both, without duplicates.' };
  }

  function readNumber(key: string, minimum: number, maximum: number): number | undefined {
    const raw = record[key];
    if (raw === undefined || raw === null) return undefined;
    if (typeof raw !== 'number' || !Number.isFinite(raw) || raw < minimum || raw > maximum) {
      throw new Error(`${key} must be a number from ${minimum} to ${maximum}, or null.`);
    }
    return raw;
  }

  try {
    const minRsi = readNumber('min_rsi', 0, 100);
    const maxRsi = readNumber('max_rsi', 0, 100);
    const maxAtrPercent = readNumber('max_atr_percent', 0, 100);
    if (maxAtrPercent === 0) {
      return { ok: false, error: 'max_atr_percent must be greater than 0 or null.' };
    }
    if (minRsi !== undefined && maxRsi !== undefined && minRsi > maxRsi) {
      return { ok: false, error: 'min_rsi cannot be greater than max_rsi.' };
    }

    return {
      ok: true,
      rules: {
        allow_signals: rawSignals as Array<'BUY' | 'SELL'>,
        ...(minRsi === undefined ? {} : { min_rsi: minRsi }),
        ...(maxRsi === undefined ? {} : { max_rsi: maxRsi }),
        ...(maxAtrPercent === undefined ? {} : { max_atr_percent: maxAtrPercent }),
      },
    };
  } catch (error) {
    return { ok: false, error: error instanceof Error ? error.message : 'Manual rules are invalid.' };
  }
}
