import { cp, mkdir, rm, writeFile } from 'node:fs/promises';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const source = path.join(root, 'backend', 'web');
const output = path.join(root, 'native-dist');
const rawApiBase = (process.env.KISANX_API_BASE || '').trim();

let apiUrl;
if (rawApiBase) {
  try {
    apiUrl = new URL(rawApiBase);
  } catch {
    throw new Error('KISANX_API_BASE must be a valid URL, such as https://api.example.com.');
  }

  const localHost = ['localhost', '127.0.0.1', '10.0.2.2'].includes(apiUrl.hostname);
  if (apiUrl.protocol !== 'https:' && !(localHost && apiUrl.protocol === 'http:')) {
    throw new Error('Use HTTPS for the hosted API. HTTP is allowed only for local development hosts.');
  }
  if (apiUrl.pathname !== '/' || apiUrl.search || apiUrl.hash || apiUrl.username || apiUrl.password) {
    throw new Error('KISANX_API_BASE must be only the API origin, without a path, query, credentials, or fragment.');
  }
}

await rm(output, { recursive: true, force: true });
await mkdir(output, { recursive: true });
await cp(source, output, { recursive: true });
const origin = apiUrl?.origin || '';
const config = `window.KISANX_API_BASE = ${JSON.stringify(origin)};\nwindow.KISANX_IS_NATIVE = true;\n`;
await writeFile(path.join(output, 'assets', 'app-config.js'), config, 'utf8');
if (origin) {
  console.log(`Prepared native web assets in ${path.relative(root, output)} for ${origin}`);
} else {
  console.warn('KISANX_API_BASE is empty. The native app will start in frontend demonstration mode; backend-dependent features need a rebuild after the HTTPS API is deployed.');
}
