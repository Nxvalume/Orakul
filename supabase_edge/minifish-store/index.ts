// MiniFish: HTTPS front end for a dedicated private Supabase Postgres schema.
// The Render application encrypts browser storage and job data before sending.
// Deployment replaces TOKEN_HASH_PLACEHOLDER with the SHA-256 of a strong secret.
import postgres from 'npm:postgres@3.4.5';

const EXPECTED_HASH = 'TOKEN_HASH_PLACEHOLDER';
const databaseUrl = Deno.env.get('SUPABASE_DB_URL') || '';
const db = postgres(databaseUrl, {
  max: 1, prepare: false, connect_timeout: 8, idle_timeout: 5,
});

const allowed = [
  /^UPDATE minifish\.mf_jobs SET /i,
  /^INSERT INTO minifish\.(?:mf_profiles|mf_jobs|mf_job_results|mf_allowed_domains)\s*\(/i,
  /^SELECT [a-z0-9_, ]+ FROM minifish\.(?:mf_profiles|mf_jobs|mf_job_results|mf_allowed_domains)\b/i,
  /^DELETE FROM minifish\.mf_profiles WHERE name=\$1$/i,
];

function permitted(input: unknown): input is string {
  if (typeof input !== 'string' || input.length > 2200) return false;
  const statement = input.replace(/\s+/g, ' ').trim();
  if (/[;]|--|\/\*|\*\//.test(statement)) return false;
  if (/\b(?:DROP|ALTER|CREATE|TRUNCATE|GRANT|REVOKE|COPY|EXECUTE|UNION|JOIN|pg_catalog|information_schema|public|auth|pg_read_file)\b/i.test(statement)) return false;
  const operations = statement.match(/\b(?:SELECT|INSERT|UPDATE|DELETE)\b/gi) || [];
  const isKnownUpsert = operations.length === 2 &&
    /^INSERT INTO minifish\.mf_profiles\s*\(/i.test(statement) &&
    /\bON CONFLICT\s*\(name\)\s*DO UPDATE SET\s+/i.test(statement);
  if (operations.length !== 1 && !isKnownUpsert) return false;
  return allowed.some((rule) => rule.test(statement));
}

function binaryToBase64(value: Uint8Array): string {
  let output = '';
  for (let i = 0; i < value.length; i += 8192) {
    output += String.fromCharCode(...value.subarray(i, i + 8192));
  }
  return btoa(output);
}

function fromParam(value: unknown): unknown {
  if (typeof value === 'object' && value !== null && Object.keys(value).length === 1 && 'binary' in value) {
    const encoded = (value as {binary:unknown}).binary;
    if (typeof encoded !== 'string' || encoded.length > 1200000) throw new Error('payload');
    return Uint8Array.from(atob(encoded), (c) => c.charCodeAt(0));
  }
  if (value === null || typeof value === 'string' || typeof value === 'number' || typeof value === 'boolean') return value;
  throw new Error('parameter');
}

function toValue(value: unknown): unknown {
  if (value instanceof Uint8Array) return {binary: binaryToBase64(value)};
  if (typeof value === 'bigint') return Number(value);
  return value;
}

async function sha256Hex(text: string): Promise<string> {
  const hash = await crypto.subtle.digest('SHA-256', new TextEncoder().encode(text));
  return [...new Uint8Array(hash)].map((n) => n.toString(16).padStart(2, '0')).join('');
}

function constantTimeEqual(a: string, b: string): boolean {
  if (a.length !== b.length) return false;
  let diff = 0;
  for (let i = 0; i < a.length; i++) diff |= a.charCodeAt(i) ^ b.charCodeAt(i);
  return diff === 0;
}

function response(data: object, status = 200): Response {
  return new Response(JSON.stringify(data), {
    status, headers: {'Content-Type':'application/json','Cache-Control':'no-store'},
  });
}

Deno.serve(async (request: Request) => {
  if (request.method !== 'POST') return response({error:'method_not_allowed'},405);
  const token = request.headers.get('x-minifish-token') || '';
  if (!/^[0-9a-f]{96}$/.test(token) ||
      !constantTimeEqual(await sha256Hex(token), EXPECTED_HASH)) {
    return response({error:'unauthorized'},401);
  }
  if ((Number(request.headers.get('content-length')) || 0) > 1500000) {
    return response({error:'payload_too_large'},413);
  }
  try {
    const body = await request.json();
    if (!permitted(body.sql) || !Array.isArray(body.params) || body.params.length > 12 ||
        typeof body.fetch !== 'boolean') {
      return response({error:'invalid_operation'},400);
    }
    const params = body.params.map(fromParam);
    const result = await db.unsafe(body.sql, params as never[]);
    if (body.fetch) {
      return response({ok:true, rows:result.map((row) => Object.values(row).map(toValue))});
    }
    return response({ok:true, rowcount:result.count || 0});
  } catch (_) {
    // Avoid reflecting database SQL, session content, keys or passwords in errors.
    return response({error:'storage_unavailable'},503);
  }
});
