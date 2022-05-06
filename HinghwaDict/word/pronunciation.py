import os

import demjson
import pydub
from django.conf import settings
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from pydub import AudioSegment as audio

from website.views import token_check, sendNotification, simpleUserInfo, upload_file
from .forms import PronunciationForm
from .models import Word, Character, Pronunciation, split
from django.utils import timezone


@csrf_exempt
def searchPronunciations(request):
    try:
        if request.method == 'GET':
            if ('token' in request.headers) and token_check(request.headers['token'], settings.JWT_KEY, -1):
                pronunciations = Pronunciation.objects.all()
            else:
                pronunciations = Pronunciation.objects.filter(visibility=True)
            if 'verifier' in request.GET:
                pronunciations = pronunciations.filter(verifier__id=request.GET['verifier'])
            if 'granted' in request.GET:
                pronunciations = pronunciations.filter(verifier__isnull=request.GET['granted'] != 'true')
            if 'word' in request.GET:
                pronunciations = pronunciations.filter(word__id=request.GET['word'])
            if 'contributor' in request.GET:
                pronunciations = pronunciations.filter(contributor__id=request.GET['contributor'])
            pronunciations = list(pronunciations)
            pronunciations.sort(key=lambda item: item.id)
            total = len(pronunciations)
            if ('order' in request.GET) and request.GET['order'] == '1':
                pronunciations.reverse()
            if 'pageSize' in request.GET:
                pageSize = int(request.GET['pageSize'])
                page = int(request.GET['page'])
                r = min(len(pronunciations), page * pageSize)
                l = min(len(pronunciations) + 1, (page - 1) * pageSize)
                pronunciations = pronunciations[l:r]
            result = []
            for pronunciation in pronunciations:
                result.append({'pronunciation': {"id": pronunciation.id, 'word_id': pronunciation.word.id,
                                                 'word_word': pronunciation.word.word, 'source': pronunciation.source,
                                                 'ipa': pronunciation.ipa, 'pinyin': pronunciation.pinyin,
                                                 'contributor': pronunciation.contributor.id,
                                                 'county': pronunciation.county, 'town': pronunciation.town,
                                                 'visibility': pronunciation.visibility,
                                                 'verifier': {
                                                     'nickname': pronunciation.verifier.user_info.nickname,
                                                     'avatar': pronunciation.verifier.user_info.avatar,
                                                     'id': pronunciation.verifier.id
                                                 } if pronunciation.verifier else None,
                                                 'granted': pronunciation.granted()},
                               'contributor': simpleUserInfo(pronunciation.contributor)})
            return JsonResponse({"pronunciation": result, 'total': total}, status=200)
        elif request.method == 'POST':
            token = request.headers['token']
            user = token_check(token, settings.JWT_KEY)
            if user:
                body = demjson.decode(request.body)
                body = body['pronunciation']
                pronunciation_form = PronunciationForm(body)
                if pronunciation_form.is_valid():
                    pronunciation = pronunciation_form.save(commit=False)
                    pronunciation.word = Word.objects.get(id=body['word'])
                    pronunciation.contributor = user
                    pronunciation.save()
                    return JsonResponse({'id': pronunciation.id}, status=200)
                else:
                    return JsonResponse({}, status=400)
            else:
                return JsonResponse({}, status=401)
        else:
            return JsonResponse({}, status=405)
    except Exception as e:
        return JsonResponse({"msg": str(e)}, status=500)


def Ipa2Pinyin(ipa) -> str:
    return ipa


@csrf_exempt
def combinePronunciation(request, ipa):
    try:
        if request.method == 'GET':
            submit_list = os.listdir(os.path.join(settings.SAVED_PINYIN, 'submit'))
            available = []
            for file in submit_list:
                if file.endswith('.mp3'):
                    available.append(file.replace('.mp3', ''))
            available = set(available)
            ipa = split(ipa)
            ans = [(len(p.ipa), p.contributor.username, p.source) for p in
                   Pronunciation.objects.filter(ipa=ipa).filter(visibility=True)]
            ans.sort(key=lambda x: x[0])
            # 这部分直接拷贝下面的V2的代码
            inputs = []
            for ipa1 in ipa.split(' '):
                inputs.append(set([Ipa2Pinyin(ipa1)]))
            results = []
            for alt_pinyin in inputs:
                if len(alt_pinyin & available) > 0:
                    result = {'pinyin': list(alt_pinyin & available)[0],
                              'dir': os.path.join(settings.SAVED_PINYIN, 'submit')}
                else:
                    result = {'pinyin': list(alt_pinyin)[0],
                              'dir': os.path.join(settings.SAVED_PINYIN, 'combine')}
                results.append(result)
            dir = os.path.join(settings.MEDIA_ROOT, 'audio', 'public')
            if not os.path.exists(dir):
                os.makedirs(dir)
            time = timezone.now().__format__("%Y_%m_%d")
            filename = time + '_' + (''.join([item['pinyin'] for item in results])) + '.mp3'
            path = os.path.join(dir, filename)
            result = MergeAudio(results, path)
            if result == 0:
                key = 'files/audio/public/' + filename.replace('_', '/')
                tts = upload_file(path, key)
            else:
                tts = 'null'

            if len(ans):
                ans = ans[0]
                return JsonResponse({'contributor': ans[1], 'url': ans[2], 'tts': tts}, status=200)
            else:
                return JsonResponse({'contributor': 'null', 'url': 'null', 'tts': tts}, status=200)
        else:
            return JsonResponse({}, status=405)
    except Exception as e:
        return JsonResponse({"msg": str(e)}, status=500)


def MergeAudio(pinyins, path):
    '''
    根据拼音列表剪辑mp3文件
    :param pinyins:拼音列表[{pinyin,dir}]
    :return: 返回结果0表示成功
    '''
    try:
        target = pydub.AudioSegment.silent(duration=100, frame_rate=44100)
        for item in pinyins:
            file = os.path.join(item['dir'], item['pinyin'] + '.mp3')
            music = audio.from_file(file)
            music.set_frame_rate(44100)
            target += music
        target.export(path, format='mp3')
        return 0
    except Exception as msg:
        return str(msg)


@csrf_exempt
def combinePronunciationV2(request):
    try:
        if request.method == 'GET':
            submit_list = os.listdir(os.path.join(settings.SAVED_PINYIN, 'submit'))
            # secondary 即保证拼音对，不保证音调的正确性
            available = []
            secondary_list = []
            for file in submit_list:
                if file.endswith('.mp3'):
                    available.append(file.replace('.mp3', ''))
                    secondary_list.append(file.replace('.mp3', '')[:-1])
            available = set(available)
            secondary = set(secondary_list)
            inputs = []
            secondary_inputs = []
            if 'words' in request.GET:
                result = Character.objects.filter(character__in=request.GET['words'])
                dic = {}
                dic1 = {}
                for character in request.GET['words']:
                    dic[character] = set()
                    dic1[character] = set()
                for character in result:
                    dic[character.character].add(character.pinyin)
                    dic1[character.character].add(character.pinyin[:-1])
                for character in request.GET['words']:
                    inputs.append(dic[character])
                    secondary_inputs.append(dic1[character])
            elif 'ipas' in request.GET:
                ipas = split(request.GET['ipas']).split(' ')
                for ipa in ipas:
                    inputs.append(set([Ipa2Pinyin(ipa)]))
                    secondary_inputs.append(set([Ipa2Pinyin(ipa)[:-1]]))
            elif 'pinyins' in request.GET:
                pinyins = split(request.GET['pinyins']).split(' ')
                for pinyin in pinyins:
                    inputs.append(set([pinyin]))
                    secondary_inputs.append(set([pinyin[:-1]]))
            results = []
            for alt_pinyin, secondary_pinyin in zip(inputs, secondary_inputs):
                if len(alt_pinyin & available) > 0:
                    result = {'pinyin': list(alt_pinyin & available)[0],
                              'dir': os.path.join(settings.SAVED_PINYIN, 'submit')}
                elif len(secondary_pinyin & secondary) > 0:
                    temp = list(secondary_pinyin & secondary)
                    a = list(alt_pinyin)
                    mi = 8
                    for x in temp:
                        shengdiaos = []
                        for y in a:
                            if y.startswith(x):
                                shengdiaos.append(int(y[-1]))
                        for i in range(1, 8):
                            pinyin = x + str(i)
                            if pinyin in available:
                                for shengdiao in shengdiaos:
                                    if abs(shengdiao - i) < mi:
                                        mi = abs(shengdiao - i)
                                        optimize_pinyin = pinyin
                    result = {'pinyin': optimize_pinyin, 'dir': os.path.join(settings.SAVED_PINYIN, 'submit')}
                else:
                    result = {'pinyin': list(alt_pinyin)[0],
                              'dir': os.path.join(settings.SAVED_PINYIN, 'combine')}
                results.append(result)
            dir = os.path.join(settings.MEDIA_ROOT, 'audio', 'public')
            if not os.path.exists(dir):
                os.makedirs(dir)
            time = timezone.now().__format__("%Y_%m_%d")
            filename = time + '_' + (''.join([item['pinyin'] for item in results])) + '.mp3'
            path = os.path.join(dir, filename)
            result = MergeAudio(results, path)
            if result == 0:
                key = 'files/audio/public/' + filename.replace('_', '/')
                url = upload_file(path, key)
                return JsonResponse({'url': url}, status=200)
            else:
                return JsonResponse({'msg': f'Merge fail,msg:{result}'}, status=500)
        else:
            return JsonResponse({}, status=405)
    except Exception as e:
        return JsonResponse({"msg": str(e)}, status=500)


@csrf_exempt
def managePronunciation(request, id):
    try:
        pronunciation = Pronunciation.objects.filter(id=id)
        if pronunciation.exists():
            pronunciation = pronunciation[0]
            if request.method == 'GET':
                pronunciation.views += 1
                pronunciation.save()
                user = pronunciation.contributor
                return JsonResponse(
                    {"pronunciation": {"id": pronunciation.id, 'word_id': pronunciation.word.id,
                                       'word_word': pronunciation.word.word, 'source': pronunciation.source,
                                       'ipa': pronunciation.ipa, 'pinyin': pronunciation.pinyin,
                                       'contributor': {"id": user.id, 'username': user.username,
                                                       'nickname': user.user_info.nickname,
                                                       'email': user.email, 'telephone': user.user_info.telephone,
                                                       'registration_time': user.date_joined.__format__(
                                                           '%Y-%m-%d %H:%M:%S'),
                                                       'login_time': user.last_login.__format__('%Y-%m-%d %H:%M:%S')
                                                       if user.last_login else '',
                                                       'birthday': user.user_info.birthday,
                                                       'avatar': user.user_info.avatar,
                                                       'county': user.user_info.county, 'town': user.user_info.town,
                                                       'is_admin': user.is_superuser}, 'county': pronunciation.county,
                                       'town': pronunciation.town, 'visibility': pronunciation.visibility,
                                       'verifier': {
                                           'nickname': pronunciation.verifier.user_info.nickname,
                                           'avatar': pronunciation.verifier.user_info.avatar,
                                           'id': pronunciation.verifier.id
                                       } if pronunciation.verifier else None,
                                       'granted': pronunciation.granted()
                                       }}, status=200)
            elif request.method == 'PUT':
                token = request.headers['token']
                if token_check(token, settings.JWT_KEY, pronunciation.contributor.id):
                    body = demjson.decode(request.body)
                    body = body['pronunciation']
                    pronunciation_form = PronunciationForm(body)
                    for key in body:
                        if (key != 'word') and len(pronunciation_form[key].errors.data):
                            return JsonResponse({}, status=400)
                    for key in body:
                        if key != 'word':
                            setattr(pronunciation, key, body[key])
                        else:
                            pronunciation.word = Word.objects.get(id=body[key])
                    pronunciation.save()
                    return JsonResponse({}, status=200)
                else:
                    return JsonResponse({}, status=401)
            elif request.method == 'DELETE':
                token = request.headers['token']
                user = token_check(token, settings.JWT_KEY, pronunciation.contributor.id)
                if user:
                    if user != pronunciation.contributor:
                        body = demjson.decode(request.body)
                        message = body["message"] if "message" in body else "管理员操作"
                        content = f'您的语音(id = {pronunciation.id}) 已被删除，理由是：\n\t{message}'
                        sendNotification(None, [pronunciation.contributor], content, target=pronunciation,
                                         title='【通知】语音处理结果')
                    pronunciation.delete()
                    return JsonResponse({}, status=200)
                else:
                    return JsonResponse({}, status=401)
            else:
                return JsonResponse({}, status=405)
        else:
            return JsonResponse({}, status=404)
    except Exception as e:
        return JsonResponse({"msg": str(e)}, status=500)


@csrf_exempt
def managePronunciationVisibility(request, id):
    '''
    管理员管理发音的visibility字段
    :param request:
    :return:
    '''
    try:
        if request.method in ['PUT', 'POST']:
            token = request.headers['token']
            user = token_check(token, settings.JWT_KEY, -1)
            if user:
                pro = Pronunciation.objects.filter(id=id)
                if pro.exists():
                    body = demjson.decode(request.body) if len(request.body) else {}
                    pro = pro[0]
                    if 'result' in body:
                        pro.visibility = body['result']
                    else:
                        pro.visibility ^= True
                    pro.verifier = user
                    if pro.visibility:
                        extra = f"，理由是:\n\t{body['reason']}" if "reason" in body else ""
                        content = f"恭喜您的语音(id ={id}) 已通过审核" + extra
                    else:
                        msg = body['reason'] if 'reason' in body else body['message']
                        content = f'很遗憾，您的语音(id = {id}) 没通过审核，理由是:\n\t{msg}'
                    sendNotification(None, [pro.contributor], content=content, target=pro, title='【通知】语音审核结果')
                    pro.save()
                    return JsonResponse({}, status=200)
                else:
                    return JsonResponse({}, status=404)
            else:
                return JsonResponse({}, status=401)
        else:
            return JsonResponse({}, status=405)
    except Exception as e:
        return JsonResponse({'msg': str(e)}, status=500)
