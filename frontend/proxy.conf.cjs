// Development only. Production serves /api/v1 through the hosting reverse proxy.
const target = process.env.BACKEND_URL || 'http://127.0.0.1:3000';
const parsed = new URL(target);
if (!['http:', 'https:'].includes(parsed.protocol) || parsed.username || parsed.password) {
  throw new Error('BACKEND_URL must be an HTTP(S) origin without embedded credentials.');
}
module.exports = {
  '/api/**': {
    target: parsed.origin,
    changeOrigin: true,
    timeout: 35000,
    proxyTimeout: 35000,
  },
};
