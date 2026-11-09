from collections import Counter
import os
import re
from flask import Flask, request
from PIL import Image
import pytesseract
import telebot
from telebot.types import InlineKeyboardButton, InlineKeyboardMarkup

# توكن البوت الجديد الخاص بك
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


# --- ميزة إرسال SMS الذكية ---


@bot.message_handler(commands=['sendsms'])
def start_sms_flow(message):
  chat_id = message.chat.id
  sms_sessions[chat_id] = {}  # تهيئة جلسة جديدة للمستخدم

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


# --- معالجة النصوص العادية (خطوات إدخال الرقم والنص + تحليل النصوص السابق) ---
@bot.message_handler(content_types=['text'])
def handle_text_messages(message):
  chat_id = message.chat.id
  text = message.text

  # التحقق إذا كان المستخدم في منتصف عملية إرسال SMS
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

      # عرض لوحة التأكيد والرسالة النهائية قبل الإرسال
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

  # إذا لم يكن في جلسة SMS، يتم تنفيذ التحليل العادي للنص (كما في البوت السابق)
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
      InlineKeyboardButton('📱 إرسال كـ SMS', callback_data='start_sms_from_text')
  )

  bot.reply_to(message, response_msg, parse_mode='Markdown', reply_markup=markup)


@bot.callback_query_handler(
    func=lambda call: call.data in ['sms_confirm', 'sms_cancel', 'start_sms_from_text']
)
def handle_sms_actions(call):
  chat_id = call.message.chat.id

  if call.data == 'start_sms_from_text':
    bot.answer_callback_query(call.id)
    # بدء عملية الـ SMS مباشرة
    start_sms_flow(call.message)
    return

  if chat_id not in sms_sessions:
    bot.answer_callback_query(call.id, 'انتهت الجلسة، ابدأ من جديد بـ /sendsms')
    return

  if call.data == 'sms_cancel':
    del sms_sessions[chat_id]
    bot.answer_callback_query(call.id, 'تم إلغاء العملية.')
    bot.edit_message_text('❌ تم إلغاء إرسال الـ SMS بنجاح.', chat_id, call.message.message_id)

  elif call.data == 'sms_confirm':
    session = sms_sessions[chat_id]
    brand = session['brand']
    phone = session['phone']
    body = session['message_body']

    bot.answer_callback_query(call.id, 'جاري الإرسال...')

    # --- هنا يتم ربط كود بوابة الإرسال الفعلي (مثل Twilio API) ---
    # مثال: send_via_twilio(phone, f"[{brand}]: {body}")

    bot.edit_message_text(
        f'🚀 **تم إرسال الرسالة بنجاح!**\n\n'
        f'• المُرسِل: {brand}\n'
        f'• إلى الرقم: {phone}\n'
        f'• النص: {body}',
        chat_id,
        call.message.message_id,
        parse_mode='Markdown',
    )
    # تنظيف الجلسة بعد الإرسال
    del sms_sessions[chat_id]


# رسالة الترحيب الرئيسية
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
