import os
from flask import Flask, request
import telebot
from telebot.types import InlineKeyboardButton, InlineKeyboardMarkup

# التوكن الصحيح والمطابق لصورتك الأخيرة
TOKEN = '9020627346:AAFRbP46t0W-MaEyzzish2enwsH0rEwrfEE'
bot = telebot.TeleBot(TOKEN)

app = Flask(__name__)

# قاموس مؤقت لحفظ جلسات إرسال الـ SMS لكل مستخدم
sms_sessions = {}


@app.route('/')
def home():
  return 'SMS Sender Bot is active and running successfully!'


@app.route(f'/{TOKEN}', methods=['POST'])
def webhook():
  if request.headers.get('content-type') == 'application/json':
    json_string = request.get_data().decode('utf-8')
    update = telebot.types.Update.de_json(json_string)
    bot.process_new_updates([update])
    return '', 200
  else:
    return 'Forbidden', 403


# --- الخطوة الأولى: بدء خدمة الـ SMS واختيار الصفة ---
@bot.message_handler(commands=['start', 'help', 'sendsms'])
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


# --- معالجة اختيار صفة المُرسِل ---
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


# --- معالجة الخطوات النصية (رقم الهاتف ثم نص الرسالة) ---
@bot.message_handler(content_types=['text'])
def handle_text_messages(message):
  chat_id = message.chat.id
  text = message.text

  if chat_id in sms_sessions:
    session = sms_sessions[chat_id]
    step = session.get('step')

    # الخطوة الثانية: استقبال رقم الهاتف وطلب النص
    if step == 'waiting_phone':
      session['phone'] = text
      session['step'] = 'waiting_text'
      bot.reply_to(
          message,
          '✍️ ممتاز! الآن أرسل **نص الرسالة** الذي تريد إرساله للمستلم:',
          parse_mode='Markdown',
      )
      return

    # الخطوة الثالثة: استقبال النص وعرض نافذة التأكيد
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
  else:
    bot.reply_to(
        message,
        'أهلاً بك! أرسل الأمر `/sendsms` لبدء إرسال رسالة SMS.',
        parse_mode='Markdown',
    )


# --- الخطوة الرابعة: التأكيد أو الإلغاء ---
@bot.callback_query_handler(
    func=lambda call: call.data in ['sms_confirm', 'sms_cancel']
)
def handle_sms_actions(call):
  chat_id = call.message.chat.id

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


if __name__ == '__main__':
  bot.remove_webhook()
  RENDER_URL = f'https://ai-sms-ocr-bot.onrender.com/{TOKEN}'
  bot.set_webhook(url=RENDER_URL)

  port = int(os.environ.get('PORT', 10000))
  app.run(host='0.0.0.0', port=port)
