from app.database.models import Post
import pytz

class SerializePost:
    def __init__(self, post: Post):
        self.post = post

    def get_images(self, amount: int = 5):
        images = self.post.images.split(',')
        return images[:amount]

    def generate_link(self):
        return f"https://bidauto.online/lot/{self.post.lot_id}?auction_name={self.post.auction.upper()}"

    def serialize(self):
        local_time = None
        if self.post.auction_date:
            vilnius_tz = pytz.timezone('Europe/Vilnius')
            local_time = self.post.auction_date.astimezone(vilnius_tz)
            local_time = local_time.strftime('%d.%m.%Y %H:%M')
        text = (
            f"🔗 <a href=\"{self.generate_link()}\">Atidaryti bidauto.online</a>\n\n"
            f"📲 Susisiekite: https://t.me/bidautoLT\n"
            f"🚗🔥 Labai geras pasiūlymas aukcione! 🔥🚗\n"
            f"🚗 <b>{self.post.title}</b>\n"
            f"🕔 <b>{self.post.odometer} miles</b>\n"
            f"⚠️ <u><b>REZERVAS: ${f'{self.post.reserve_price:,}' if self.post.reserve_price else 'N/A'}</b></u>\n"
            f"📌 Pardavėjas: Draudimas 👍\n"
            f"📌 VIN: {self.post.vin}\n"
            f"📌 Būklė: {self.post.status}\n"
            f"📌 Dokumentai: Tinka registracijai 👍\n"
            f"⏳ Aukcionas prasideda: {local_time if local_time else 'N/A'} (Vilnius)\n"
            f"🛳️ Transporto išlaidos sudarys:\n"
            f"Vietinis Transportas: ${self.post.delivery_price}\n"
            f"Jūrinis pervežimas: ${self.post.shipping_price}\n"
            f"Broker Fee: $299\n"
            f"*** Taip pat prisidės aukciono mokesčiai, kurie priklauso nuo statymo sumos!\n"
            f"🇱🇹 Lietuvoje liks sumokėti:\n"
            f"✅ 10% Muitas\n"
            f"✅ 21% PVM\n"
            f"✅ 350€ Krova\n"
            f"⏳ Liko mažai laiko – nepraleiskite progos! ⏳💨\n"
            f"💸 VIDUTINĖ pardavimo kaina: ${self.post.average_sell_price if self.post.average_sell_price else 'N/A'}\n"
            f"✉️ Rašykite mums DM arba apsilankykite 👉 bidauto.online\n\n"
        )
        return text