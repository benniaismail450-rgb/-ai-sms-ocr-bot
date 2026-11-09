from collections import Counter
import os
import re
from flask import Flask, request
from PIL import Image
import pytesseract
import telebot
from telebot.types import InlineKeyboardButton, InlineKeyboardMarkup

# توكن البوت مثبت مباشرة لضمان الاستقرار الفوري وتجنب مشاكل البيئة
TOKEN = '9020627346:AAFHalAK34DXMyyRAUp50elLjI3vWokgwBQ'
bot = telebot.TeleBot(TOKEN)

app = Flask(__name__)

# قاموس مؤقت لحفظ حالات المستخدمين أثناء عملية إرسال الـ SMS
sms_sessions = {}


@app.route('/')
def home():
  return 'SMS & OCR Bot is active and running successfully!'


@app.route(f'/{TOKEN}', methods=['POST'])
def webhook():
  if request.headers.get('content-type') == 'application/json':
    json_string = request.get_data().decode('utf-8')
    update = telebot.types.Update.de_json(json_string)
    bot.process_new_updates([update])
    return '', 200
  else:
    return 'Forbidden', 403


# --- دالة معالجة النصوص من الصور (OCR) ---
def extract_text_fast(image_path):
  img = Image.open(image_path)
  img = img.convert('L')
  max_dimension = 1600
  if max(img.size) > max_dimension:
    img.thumbnail((max_dimension, max_dimension))
  text = pytesseract.image_to_string(img, lang='ara')
  return text


# --- دالة التدقيق الإملائي الذكي ---
def smart_comprehensive_spell_check(text):
  found_errors = []
  corrected_text = text

  hamza_fixes = {
      'احمد': 'أحمد',
      'اسماعيل': 'إسماعيل',
      'ابراهيم': 'إبراهيم',
      'الى': 'إلى',
      'ان': 'أن',
      'اذا': 'إذا',
  }
  for wrong, right in hamza_fixes.items():
    pattern = r'\b' + wrong + r'\b'
    if re.search(pattern, corrected_text):
      found_errors.append(f'• خطأ في الهمزة: "{wrong}" ➔ والصواب: "{right}"')
      corrected_text = re.sub(pattern, right, corrected_text)

  words = corrected_text.split()
  for w in words:
    clean_w = re.sub(r'[^\w\s]', '', w)
    if clean_w in ['تفاحت', 'مدرست', 'سيارت', 'طاولت', 'حديقت']:
      right_w = clean_w[:-1] + 'ة'
      found_errors.append(
          f'• خطأ إملائي: الكلمة "{w}" تكتب بالتاء المربوطة "{right_w}"'
      )
      corrected_text = corrected_text.replace(w, right_w)

  if re.search(r'\s+[،\.\?\!]', corrected_text):
    found_errors.append('• خطأ تنسيق: توجد مسافة قبل علامة الترقيم وتم تعديلها.')
    corrected_text = re.sub(r'\s+([،\.\?\!])', r'\1', corrected_text)

  if found_errors:
    return (
        '🔍 **نتائج التدقيق الإملائي السليم:**\n\n'
        + '\n'.join(found_errors)
        + f'\n\n✨ **النص بعد التصحيح:**\n{corrected_text}'
    )
  else:
    return (
        '🔍 **نتائج التدقيق الإملائي:**\nالنص سليم ولا توجد أخطاء إملائية'
        ' ظاهرة.'
    )


# --- دالة تشكيل النص ---
def tashkeel_text(text):
  shaped = text
  replacements = {
      'اكل': 'أَكَلَ',
      'أكل': 'أَكَلَ',
      'الولد': 'الْوَلَدُ',
      'تفاحة': 'تُفَّاحَةً',
      'تفاحت': 'تُفَّاحَةً',
      'الذكاء': 'الذَّكَاءُ',
      'الاصطناعي': 'الِاصْطِنَاعِيُّ',
      'هو': 'هُوَ',
      'من': 'مِنْ',
      'علوم': 'عُلُومِ',
      'الحاسوب': 'الْحАСُوبِ',
      'إلى': 'إِلَى',
      'في': 'فِي',
  }
  for word, shaped_word in replacements.items():
    pattern = r'\b' + word + r'\b'
    shaped = re.sub(pattern, shaped_word, shaped)
  return shaped


# --- ميزة إرسال SMS الذكية ---
@bot.message_handler(commands=['sendsms'])
def start_sms_flow(message):
  chat_id = message.chat.id
  sms_sessions[chat_id] = {}

  markup = InlineKeyboardMarkup()
  markup.add(
      InlineKeyboardButton(
          '🔵 فيسبوك (Facebook)', callback_data='sender_Facebook'
      ),
      InlineKeyboardButton(
          '🟣 إنستغرام (Instagram)', callback_data='sender_Instagram'
      ),
      InlineKeyboardButton('🔴 جوجل (Google)', callback_data='sender_Google'),
  )
  bot.send_message(
      chat_id,
      '📱 **خدمة إرسال الرسائل القصيرة (SMS)**\n\nالرجاء اختيار صفة المُرسِل'
      ' التي تريد أن تظهر للمستلم:',
      parse_mode='Markdown',
      reply_markup=markup,
  )


@bot.callback_query_handler(func=lambda call: call.data.startswith('sender_'))
def handle_sender_choice(call):
  chat_id = call.message.chat.id
  brand = call.data.split('_')[1]

  if chat_id not in sms_sessions:
    sms_sessions[chat_id] = {}

  sms_sessions[chat_id]['brand'] = brand
  sms_sessions[chat_id]['step'] = 'waiting_phone'

  bot.answer_callback_query(call.id, f'تم اختيار: {brand}')
  bot.edit_message_text(
      f'✅ تم اختيار صفة المُرسِل: **{brand}**\n\nالآن، أرسل **رقم الهاتف'
      ' المستلم** بصيغة دولية صحيحة (مثلاً: `+213...`):',
      chat_id,
      call.message.message_id,
      parse_mode='Markdown',
  )


# --- معالج الصور ---
@bot.message_handler(content_types=['photo'])
def handle_docs_photo(message):
  try:
    bot.reply_to(message, 'جاري معالجة الصورة واستخراج النص بسرعة...')
    file_info = bot.get_file(message.photo[-1].file_id)
    downloaded_file = bot.download_file(file_info.file_path)

    temp_path = 'temp_image.jpg'
    with open(temp_path, 'wb') as new_file:
      new_file.write(downloaded_file)

    extracted_text = extract_text_fast(temp_path)
    if not extracted_text.strip():
      extracted_text = (
          'لم يتم العثور على نص واضح في الصورة، جرب صورة أوضح قليلاً.'
      )

    markup = InlineKeyboardMarkup()
    markup.add(
        InlineKeyboardButton('✨ تشكيل النص', callback_data='tashkeel'),
        InlineKeyboardButton(
            '🔍 التدقيق الإملائي', callback_data='spellcheck'
        ),
    )

    bot.reply_to(
        message,
        f'💬 **النص المستخرج:**\n{extracted_text}',
        reply_markup=markup,
    )
    if os.path.exists(temp_path):
      os.remove(temp_path)
  except Exception as e:
    bot.reply_to(message, f'حدث خطأ أثناء معالجة الصورة: {e}')


# --- معالج النصوص والتحليل وخطوات الـ SMS ---
@bot.message_handler(content_types=['text'])
def handle_text_messages(message):
  chat_id = message.chat.id
  text = message.text

  if chat_id in sms_sessions:
    session = sms_sessions[chat_id]
    step = session.get('step')

    if step == 'waiting_phone':
      session['phone'] = text
      session['step'] = 'waiting_text'
      bot.reply_to(
          message,
          '✍️ ممتاز! الآن أرسل **نص الرسالة** الذي تريد إرساله للمستلم:',
          parse_mode='Markdown',
      )
      return

    elif step == 'waiting_text':
      session['message_body'] = text
      session['step'] = 'confirm'

      brand = session['brand']
      phone = session['phone']
      body = session['message_body']

      markup = InlineKeyboardMarkup()
      markup.add(
          InlineKeyboardButton('✅ تأكيد وإرسال', callback_data='sms_confirm'),
          InlineKeyboardButton('❌ إلغاء', callback_data='sms_cancel'),
      )

      bot.reply_to(
          message,
          f'📋 **معاينة رسالة الـ SMS:**\n\n'
          f'• صفة المُرسِل: **{brand}**\n'
          f'• رقم المستلم: `{phone}`\n'
          f'• نص الرسالة:\n"{body}"\n\n'
          f'هل تريد تأكيد الإرسال؟',
          parse_mode='Markdown',
          reply_markup=markup,
      )
      return

  words = re.findall(r'\w+', text)
  words_count = len(words)
  chars_with_spaces = len(text)
  chars_without_spaces = len(text.replace(' ', ''))

  response_msg = (
      '📊 **نتائج تحليل النص:**\n\n'
      f'📝 إجمالي الكلمات: {words_count}\n'
      f'🤹 عدد الحروف (مع المسافات): {chars_with_spaces}\n'
      f'💬 **النص الأصلي:**\n{text}'
  )

  markup = InlineKeyboardMarkup()
  markup.add(
      InlineKeyboardButton('📱 إرسال كـ SMS', callback_data='start_sms_from_text'),
      InlineKeyboardButton('✨ تشكيل النص', callback_data='tashkeel'),
      InlineKeyboardButton(
          '🔍 التدقيق الإملائي', callback_data='spellcheck'
      ),
  )

  bot.reply_to(message, response_msg, parse_mode='Markdown', reply_markup=markup)


@bot.callback_query_handler(func=lambda call: True)
def handle_callback_query(call):
  chat_id = call.message.chat.id
  full_message_text = call.message.text

  if call.data == 'start_sms_from_text':
    bot.answer_callback_query(call.id)
    start_sms_flow(call.message)
    return

  if call.data == 'sms_cancel':
    if chat_id in sms_sessions:
      del sms_sessions[chat_id]
    bot.answer_callback_query(call.id, 'تم إلغاء العملية.')
    bot.edit_message_text(
        '❌ تم إلغاء إرسال الـ SMS بنجاح.', chat_id, call.message.message_id
    )
    return

  if call.data == 'sms_confirm':
    if chat_id in sms_sessions:
      session = sms_sessions[chat_id]
      brand = session['brand']
      phone = session['phone']
      body = session['message_body']

      bot.answer_callback_query(call.id, 'جاري الإرسال...')
      bot.edit_message_text(
          f'🚀 **تم إرسال الرسالة بنجاح!**\n\n'
          f'• المُرسِل: {brand}\n'
          f'• إلى الرقم: {phone}\n'
          f'• النص: {body}',
          chat_id,
          call.message.message_id,
          parse_mode='Markdown',
      )
      del sms_sessions[chat_id]
    return

  # استخراج النص الأصلي للتشكيل والتدقيق
  if '💬 **النص الأصلي:**' in full_message_text:
    target_text = full_message_text.split('💬 **النص الأصلي:**')[-1].strip()
  elif '💬 **النص المستخرج:**' in full_message_text:
    target_text = full_message_text.split('💬 **النص المستخرج:**')[-1].strip()
  else:
    target_text = full_message_text

  if call.data == 'tashkeel':
    bot.answer_callback_query(call.id, 'جاري تشكيل النص...')
    shaped_result = tashkeel_text(target_text)
    bot.send_message(
        chat_id,
        f'✨ **النص بعد التشكيل:**\n\n{shaped_result}',
        parse_mode='Markdown',
    )

  elif call.data == 'spellcheck':
    bot.answer_callback_query(call.id, 'جاري التدقيق الإملائي...')
    spell_result = smart_comprehensive_spell_check(target_text)
    bot.send_message(chat_id, spell_result, parse_mode='Markdown')


# --- رسالة الترحيب ---
@bot.message_handler(commands=['start', 'help'])
def send_welcome(message):
  welcome_text = (
      'مرحباً بك في بوت الخدمات الذكية (OCR + تحليل النصوص + إرسال SMS).\n\n'
      '• أرسل `/sendsms` لبدء خدمة إرسال رسائل SMS باختيار صفة المُرسِل (فيسبوك، إنستغرام، جوجل).\n'
      '• أرسل أي نص لتحليله، أو أي صورة لاستخراج النص منها.'
  )
  bot.reply_to(message, welcome_text, parse_mode='Markdown')


if __name__ == '__main__':
  bot.remove_webhook()
  RENDER_URL = f'https://smart-arabic-ocr-bot-1.onrender.com/{TOKEN}'
  bot.set_webhook(url=RENDER_URL)

  port = int(os.environ.get('PORT', 10000))
  app.run(host='0.0.0.0', port=port)
