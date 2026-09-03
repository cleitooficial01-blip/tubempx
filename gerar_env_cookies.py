import base64

# Script para gerar a variável YOUTUBE_COOKIES em base64
print('=' * 60)
print('GERADOR DE YOUTUBE_COOKIES PARA RENDER')
print('=' * 60)

cookies_file = 'cookies.txt'

try:
    with open(cookies_file, 'rb') as f:
        cookies_content = f.read()

    # Converter para base64
    cookies_base64 = base64.b64encode(cookies_content).decode('utf-8')

    print('\n✅ Cookies convertidos para base64!')
    print('\n📋 COPIE O VALOR ABAIXO:')
    print('-' * 60)
    print(cookies_base64)
    print('-' * 60)

    print('\n📝 INSTRUÇÕES:')
    print('1. Acesse: https://dashboard.render.com/')
    print('2. Vá no serviço TubeMPX')
    print('3. Environment → Add Environment Variable')
    print('4. Key: YOUTUBE_COOKIES')
    print('5. Value: [Cole o valor acima]')
    print('6. Save Changes')
    print('\n✅ Depois disso o site vai funcionar no Render!')

except Exception as e:
    print(f'\n❌ Erro: {e}')
