import { createReadStream, existsSync, statSync } from 'node:fs'
import { createServer, request as createRequest } from 'node:http'
import path from 'node:path'
import { fileURLToPath } from 'node:url'

const here = path.dirname(fileURLToPath(import.meta.url))
const dist = path.join(here, 'dist')
const host = '127.0.0.1'
let port = Number(process.env.PORT || 5174)

if (!existsSync(path.join(dist, 'index.html'))) {
  console.error('Frontend build not found. Run the project build first, or ask for help rebuilding it.')
  process.exit(1)
}

const types = {
  '.css': 'text/css; charset=utf-8',
  '.html': 'text/html; charset=utf-8',
  '.ico': 'image/x-icon',
  '.js': 'text/javascript; charset=utf-8',
  '.json': 'application/json; charset=utf-8',
  '.png': 'image/png',
  '.svg': 'image/svg+xml',
  '.webp': 'image/webp',
}

const server = createServer((incoming, outgoing) => {
  const pathname = new URL(incoming.url || '/', `http://${incoming.headers.host || `${host}:${port}`}`).pathname

  if (pathname === '/api' || pathname.startsWith('/api/')) {
    const apiPath = `${pathname.slice(4) || '/'}${new URL(incoming.url || '/', `http://${host}:${port}`).search}`
    const upstream = createRequest({
      hostname: '127.0.0.1',
      port: 8001,
      path: apiPath,
      method: incoming.method,
      headers: { ...incoming.headers, host: '127.0.0.1:8001' },
    }, (response) => {
      outgoing.writeHead(response.statusCode || 502, response.headers)
      response.pipe(outgoing)
    })
    upstream.on('error', () => {
      if (!outgoing.headersSent) outgoing.writeHead(502, { 'Content-Type': 'application/json; charset=utf-8' })
      outgoing.end(JSON.stringify({ detail: 'CampusAI backend is not running at http://127.0.0.1:8001.' }))
    })
    incoming.pipe(upstream)
    return
  }

  let requestedPath
  try {
    requestedPath = decodeURIComponent(pathname)
  } catch {
    outgoing.writeHead(400).end('Invalid URL')
    return
  }

  const file = path.resolve(dist, `.${requestedPath}`)
  if (file !== dist && !file.startsWith(`${dist}${path.sep}`)) {
    outgoing.writeHead(403).end('Forbidden')
    return
  }

  const target = existsSync(file) && statSync(file).isFile()
    ? file
    : path.join(dist, 'index.html')
  outgoing.writeHead(200, {
    'Content-Type': types[path.extname(target).toLowerCase()] || 'application/octet-stream',
    'Cache-Control': target.endsWith('index.html') ? 'no-cache' : 'public, max-age=3600',
  })
  if (incoming.method === 'HEAD') outgoing.end()
  else createReadStream(target).pipe(outgoing)
})

function listen(candidatePort) {
  port = candidatePort
  server.once('error', (error) => {
    if (error.code === 'EADDRINUSE' && !process.env.PORT) {
      listen(candidatePort + 1)
      return
    }
    console.error(`Could not start CampusAI frontend: ${error.message}`)
    process.exitCode = 1
  })
  server.listen(port, host, () => {
    console.log(`CampusAI frontend: http://${host}:${port}`)
    console.log('API requests are forwarded to http://127.0.0.1:8001.')
  })
}

listen(port)
