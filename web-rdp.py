import aiohttp
import aiohttp.web
from ws import inputWS,streamWS

async def getHTML(*args):
    with open('src/stream.html', 'r') as f:
        html = f.read()
    return aiohttp.web.Response(body=html, content_type='text/html', status=200, charset='utf-8')

async def getJS(*args):
    with open('src/script.js', 'r') as f:
        js = f.read()
    return aiohttp.web.Response(body=js, content_type='application/javascript', status=200, charset='utf-8')

async def getCSS(*args):
    with open('src/style.css', 'r') as f:
        style = f.read()
    return aiohttp.web.Response(body=style, content_type='text/css', status=200, charset='utf-8')

async def getKeys(*args):
    with open('src/keys.json', 'r') as f:
        keys = f.read()
    return aiohttp.web.Response(body=keys, content_type='text/json', status=200, charset='utf-8')

def main():

    app = aiohttp.web.Application()
    app.router.add_get('/', getHTML)
    app.router.add_get('/script.js', getJS)
    app.router.add_get('/style.css', getCSS)
    app.router.add_get('/keys.json', getKeys)
    app.router.add_get('/inputWS', inputWS)
    app.router.add_get('/streamWS', streamWS)

    aiohttp.web.run_app(app=app, port=7417) 

main()