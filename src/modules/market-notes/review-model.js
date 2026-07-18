export function buildMarketReviewPayload(values = {}) {
  return {
    result: values.result || '未结算',
    actual_score: values.actualScore || '',
    actual_lineup: values.actualLineup || '',
    key_turns: values.keyTurns || '',
    correct_points: values.correctPoints || '',
    wrong_points: values.wrongPoints || '',
    missing_evidence: values.missingEvidence || '',
    calibration: values.calibration || '',
    destinations: ['market_notes'],
    confirmed: false,
  };
}

export async function requestMarketReview(fetchImpl, url, options) {
  try {
    const response = await fetchImpl(url, options);
    const data = await response.json().catch(() => ({}));
    return { ok: response.ok, response, data, detail: data.detail || '' };
  } catch (error) {
    const message = error instanceof Error ? error.message : String(error || '未知错误');
    return {
      ok: false,
      response: null,
      data: {},
      detail: `网络请求失败：${message}`,
    };
  }
}
