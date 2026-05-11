// Bhakti Marg AI Load Test Configuration
import http from 'k6/http';
import { check, sleep } from 'k6';
import { Rate, Trend } from 'k6/metrics';

// Custom metrics
const askLatency = new Trend('ask_latency');
const searchLatency = new Trend('search_latency');
const errorRate = new Rate('errors');

// Test configuration
export const options = {
  stages: [
    { duration: '30s', target: 10 },   // Ramp up
    { duration: '1m', target: 50 },     // Steady load
    { duration: '30s', target: 100 },  // Stress test
    { duration: '1m', target: 100 },   // Hold
    { duration: '30s', target: 0 },    // Ramp down
  ],
  thresholds: {
    'ask_latency': ['p(95)<2000'],     // 95% under 2s
    'search_latency': ['p(95)<500'],    // 95% under 500ms
    'errors': ['rate<0.1'],             // Error rate < 10%
    'http_req_duration': ['p(95)<3000'],
  },
};

// Test data
const queries = [
  'भक्ति क्या है?',
  'प्रेम भक्ति कैसे करें?',
  'महाराज जी बताइए कि ध्यान कैसे करना चाहिए',
  'गुरु की महत्ता क्या है?',
  'आत्मज्ञान कैसे प्राप्त करें?',
];

export function setup() {
  // Check if API is running
  const res = http.get(__ENV.BASE_URL + '/api/admin/health');
  if (res.status !== 200) {
    throw new Error('API health check failed');
  }
  return { apiKey: __ENV.API_KEY || '' };
}

export default function(data) {
  const baseUrl = __ENV.BASE_URL || 'http://localhost:8000';
  const headers = {
    'Content-Type': 'application/json',
  };

  if (data.apiKey) {
    headers['X-API-Key'] = data.apiKey;
  }

  // Test 1: Ask question (most important)
  const query = queries[Math.floor(Math.random() * queries.length)];
  const start = Date.now();
  const askRes = http.post(
    `${baseUrl}/api/ask`,
    JSON.stringify({ query }),
    { headers }
  );
  askLatency.add(Date.now() - start);

  const askSuccess = check(askRes, {
    'ask status 200': (r) => r.status === 200,
    'ask has answer': (r) => r.json('answer') !== undefined,
  });
  errorRate.add(!askSuccess);

  sleep(1);

  // Test 2: List videos (paginated)
  const page = Math.floor(Math.random() * 3) + 1;
  const searchStart = Date.now();
  const videoRes = http.get(
    `${baseUrl}/api/videos?page=${page}&page_size=20`,
    { headers }
  );
  searchLatency.add(Date.now() - searchStart);

  check(videoRes, {
    'videos status 200': (r) => r.status === 200,
    'videos has items': (r) => r.json('items') !== undefined,
  });

  sleep(1);

  // Test 3: List QA pairs
  const qaRes = http.get(
    `${baseUrl}/api/qa?page=1&page_size=20`,
    { headers }
  );

  check(qaRes, {
    'qa status 200': (r) => r.status === 200,
    'qa has items': (r) => r.json('items') !== undefined,
  });

  sleep(1);
}

export function handleSummary(data) {
  return {
    'stdout': textSummary(data, { indent: ' ', enableColors: true }),
    'k6-summary.json': JSON.stringify(data, null, 2),
  };
}

function textSummary(data, opts) {
  const indent = opts.indent || '';
  const output = [];

  output.push('\n' + indent + '='.repeat(50));
  output.push(indent + 'Bhakti Marg AI Load Test Summary');
  output.push(indent + '='.repeat(50));

  // HTTP metrics
  const httpStats = data.metrics.http_req_duration;
  if (httpStats) {
    output.push(indent + '\nHTTP Request Duration:');
    output.push(indent + `  p(50): ${(httpStats.values['p(50)'] || 0).toFixed(2)}ms`);
    output.push(indent + `  p(95): ${(httpStats.values['p(95)'] || 0).toFixed(2)}ms`);
    output.push(indent + `  p(99): ${(httpStats.values['p(99)'] || 0).toFixed(2)}ms`);
  }

  // Custom metrics
  const askStats = data.metrics.ask_latency;
  if (askStats) {
    output.push(indent + '\nAsk Endpoint Latency:');
    output.push(indent + `  p(95): ${(askStats.values['p(95)'] || 0).toFixed(2)}ms`);
  }

  const errorRateVal = data.metrics.errors;
  if (errorRateVal) {
    output.push(indent + '\nError Rate: ' + ((errorRateVal.values.rate || 0) * 100).toFixed(2) + '%');
  }

  // Checks
  const checks = data.metrics.checks;
  if (checks) {
    output.push(indent + '\nChecks Passed: ' + ((checks.values.passes / (checks.values.passes + checks.values.failures)) * 100).toFixed(1) + '%');
  }

  output.push(indent + '\nTotal Requests: ' + data.metrics.http_reqs.values.count);
  output.push(indent + '='.repeat(50) + '\n');

  return output.join('\n');
}