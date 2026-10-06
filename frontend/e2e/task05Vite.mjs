process.env.QA_BACKEND_PORT = '8028';
process.env.QA_FRONTEND_PORT = '5198';
const { createServer } = await import('vite');
const server = await createServer({ configFile: 'vite.qa.config.js' });
await server.listen();
