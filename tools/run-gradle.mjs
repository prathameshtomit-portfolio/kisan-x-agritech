import { spawn } from 'node:child_process';
import path from 'node:path';

const androidDir = path.resolve('android');
const wrapper = path.join(androidDir, process.platform === 'win32' ? 'gradlew.bat' : 'gradlew');
const child = spawn(wrapper, process.argv.slice(2), {
  cwd: androidDir,
  stdio: 'inherit',
  shell: process.platform === 'win32',
});

child.on('error', error => {
  console.error(`Could not start the Android Gradle wrapper: ${error.message}`);
  process.exitCode = 1;
});
child.on('exit', (code, signal) => {
  process.exitCode = code ?? (signal ? 1 : 0);
});
