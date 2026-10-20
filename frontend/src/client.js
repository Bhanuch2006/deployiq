export const DEFAULT_REGION = 'us-east-1';

export function validateConfig(config) {
  try {
    const url = new URL(config.apiUrl);
    if (url.protocol !== 'https:' || !/^[a-z0-9]+\.execute-api\.us-east-1\.amazonaws\.com$/.test(url.hostname) || url.username || url.password || url.search || url.hash || !/^\/?$/.test(url.pathname)) return false;
    return /^[a-z0-9]{10,128}$/.test(config.clientId);
  } catch { return false; }
}

export async function cognito(action, body) {
  const response = await fetch(`https://cognito-idp.${DEFAULT_REGION}.amazonaws.com/`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/x-amz-json-1.1', 'X-Amz-Target': `AWSCognitoIdentityProviderService.${action}` },
    body: JSON.stringify(body),
  });
  const result = await response.json();
  if (!response.ok) {
    const code = String(result.__type || '').split('#').pop();
    const messages = {
      NotAuthorizedException: 'Username or password is incorrect, or your temporary password has expired.',
      UserNotFoundException: 'Username or password is incorrect.',
      PasswordResetRequiredException: 'Ask your workspace administrator to reset your password.',
      InvalidPasswordException: 'Use at least 12 characters with uppercase, lowercase, a number, and a symbol.',
      TooManyRequestsException: 'Too many sign-in attempts. Wait a moment and try again.',
    };
    throw new Error(messages[code] || 'Sign-in failed. Check your connection settings and try again.');
  }
  return result;
}

export async function request(config, token, path, signal) {
  const response = await fetch(config.apiUrl.replace(/\/$/, '') + path, {
    headers: { Authorization: `Bearer ${token}` }, signal,
  });
  const result = await response.json();
  if (!response.ok) {
    const error = new Error(response.status === 401 ? 'Your session has expired. Sign in again.' : result.message || 'Unable to load pipeline history.');
    error.status = response.status;
    throw error;
  }
  return result;
}

export function runStats(runs) {
  const passed = runs.filter(run => run.conclusion === 'success').length;
  const failed = runs.filter(run => ['failure', 'timed_out'].includes(run.conclusion)).length;
  const evaluated = passed + failed;
  return { total: runs.length, passed, failed, successRate: evaluated ? Math.round(passed / evaluated * 100) : null, diagnosed: runs.filter(run => run.analysis_status === 'completed').length };
}

export function diagnosisLabel(run) {
  if (!run) return 'Pending';
  if (run.analysis_source === 'bedrock') return 'Bedrock AI';
  if (run.analysis_source === 'groq') return 'Groq AI';
  if (run.analysis_source === 'rules') return 'Rules';
  return run.analysis_status === 'failed' ? 'Analysis failed' : 'Pending';
}

export function githubUrl(value) {
  try { const url = new URL(value); return url.protocol === 'https:' && url.hostname === 'github.com' ? url.href : null; }
  catch { return null; }
}
