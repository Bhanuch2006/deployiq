import test from 'node:test';
import assert from 'node:assert/strict';
import { runStats, diagnosisLabel, validateConfig, githubUrl } from './client.js';

test('success rate excludes cancellations and empty history is unknown', () => {
  assert.equal(runStats([]).successRate, null);
  const stats = runStats([{conclusion:'success'}, {conclusion:'failure'}, {conclusion:'cancelled'}]);
  assert.equal(stats.successRate, 50);
  assert.equal(stats.total, 3);
});
test('rules results are never presented as Bedrock AI', () => {
  assert.equal(diagnosisLabel({analysis_source:'rules', analysis_status:'completed'}), 'Rules');
  assert.equal(diagnosisLabel({analysis_source:'bedrock'}), 'Bedrock AI');
  assert.equal(diagnosisLabel({analysis_source:'groq'}), 'Groq AI');
});
test('only HTTPS API Gateway origins are accepted for bearer tokens', () => {
  assert.equal(validateConfig({apiUrl:'https://abc123.execute-api.us-east-1.amazonaws.com',clientId:'abc123456789'}), true);
  for (const apiUrl of ['http://abc123.execute-api.us-east-1.amazonaws.com', 'https://evil.example', 'https://abc123.execute-api.us-east-1.amazonaws.com/extra']) {
    assert.equal(validateConfig({apiUrl,clientId:'abc123456789'}), false);
  }
});
test('workflow links cannot execute scripts or lead to unrelated hosts', () => {
  assert.equal(githubUrl('javascript:alert(1)'), null);
  assert.equal(githubUrl('https://example.com'), null);
  assert.equal(githubUrl('https://github.com/team/repo/actions/runs/123'), 'https://github.com/team/repo/actions/runs/123');
});
