import pyaudio
import wave
import threading
import time
from datetime import datetime
import os
from dataclasses import dataclass, field
from typing import List, Optional, Dict, Any, Tuple
import glob

folder_path = "kayitlar/"
@dataclass
class KayitDurumu:
    aktif: bool = False
    sure: float = 0.0
    frame_sayisi: int = 0
    mesaj: str = ""
    baslangic_zamani: Optional[float] = None

    def guncelle_sure(self) -> None:
        """Başlangıç zamanından itibaren geçen süreyi hesaplar"""
        if self.aktif and self.baslangic_zamani:
            self.sure = time.time() - self.baslangic_zamani



@dataclass
class KayitDosyasi:
    """Kayıt dosyası bilgilerini tutan dataclass"""
    ad: str
    yol: str
    boyut: int
    tarih: datetime

    def boyut_kb(self) -> float:
        """Dosya boyutunu KB cinsinden döndürür"""
        return self.boyut / 1024

    def boyut_mb(self) -> float:
        """Dosya boyutunu MB cinsinden döndürür"""
        return self.boyut / (1024 * 1024)


@dataclass
class SesAyarlari:
    """Ses kayıt ayarlarını tutan dataclass"""
    sample_rate: int = 44100
    channels: int = 1
    chunk: int = 1024
    format: int = field(default_factory=lambda: pyaudio.paInt16)

    def __post_init__(self):
        """Dataclass oluşturulduktan sonra çağrılır"""
        self.validate()

    def validate(self) -> None:
        """Ayarları doğrular"""
        if self.sample_rate not in [8000, 16000, 22050, 44100, 48000, 96000]:
            raise ValueError(f"Geçersiz sample_rate: {self.sample_rate}")

        if self.channels not in [1, 2]:
            raise ValueError(f"Geçersiz channels: {self.channels}")

        if self.chunk not in [256, 512, 1024, 2048, 4096]:
            raise ValueError(f"Geçersiz chunk: {self.chunk}")


@dataclass
class SesKaydedici:
    """
    Dataclass tabanlı kontrol edilebilir ses kayıt sınıfı
    """
    # Ses ayarları
    ayarlar: SesAyarlari = field(default_factory=SesAyarlari)

    # Private alanlar (post_init'te initialize edilir)
    _durum: KayitDurumu = field(default_factory=KayitDurumu, init=False)
    _frames: List[bytes] = field(default_factory=list, init=False)
    _audio: Optional[pyaudio.PyAudio] = field(default=None, init=False)
    _stream: Optional[pyaudio.Stream] = field(default=None, init=False)
    _kayit_thread: Optional[threading.Thread] = field(default=None, init=False)
    _lock: threading.Lock = field(default_factory=threading.Lock, init=False)

    def __post_init__(self):
        """Dataclass oluşturulduktan sonra çağrılır"""
        self._durum.mesaj = "Kayıt için hazır"

    @property
    def kayit_devam_ediyor(self) -> bool:
        """Thread-safe kayıt durumu kontrolü"""
        with self._lock:
            return self._durum.aktif

    @property
    def frame_sayisi(self) -> int:
        """Thread-safe frame sayısı"""
        with self._lock:
            return len(self._frames)

    def kayit_baslat(self) -> bool:
        """Kayıt başlatır"""
        with self._lock:
            if self._durum.aktif:
                self._durum.mesaj = "Kayıt zaten devam ediyor!"
                return False

            try:
                # PyAudio'yu başlat
                self._audio = pyaudio.PyAudio()

                # Mikrofon var mı kontrol et
                if self._audio.get_device_count() == 0:
                    self._durum.mesaj = "Mikrofon bulunamadı!"
                    self._audio.terminate()
                    return False

                # Stream'i aç
                self._stream = self._audio.open(
                    format=self.ayarlar.format,
                    channels=self.ayarlar.channels,
                    rate=self.ayarlar.sample_rate,
                    input=True,
                    frames_per_buffer=self.ayarlar.chunk,
                    input_device_index=None  # Varsayılan mikrofon
                )

                # Kayıt durumunu aktif et
                self._durum.aktif = True
                self._durum.baslangic_zamani = time.time()
                self._durum.frame_sayisi = 0
                self._frames.clear()

                # Kayıt thread'ini başlat
                self._kayit_thread = threading.Thread(target=self._kayit_dongusu)
                self._kayit_thread.daemon = True
                self._kayit_thread.start()

                self._durum.mesaj = "Kayıt başlatıldı!"
                return True

            except Exception as e:
                self._durum.mesaj = f"Kayıt başlatılamadı: {str(e)}"
                self._temizle()
                return False

    def kayit_durdur(self) -> bool:
        """Kayıt durdurur"""
        with self._lock:
            if not self._durum.aktif:
                self._durum.mesaj = "Kayıt zaten durmuş!"
                return False

            self._durum.aktif = False
            self._durum.mesaj = "Kayıt durduruluyor..."

        # Thread'in bitmesini bekle (lock dışında)
        if self._kayit_thread and self._kayit_thread.is_alive():
            self._kayit_thread.join(timeout=2)

        with self._lock:
            self._temizle()
            self._durum.mesaj = "Kayıt durduruldu!"
            return True

    def _kayit_dongusu(self) -> None:
        """Kayıt döngüsü (thread içinde çalışır)"""
        try:
            while True:
                with self._lock:
                    if not self._durum.aktif or not self._stream:
                        break

                    try:
                        data = self._stream.read(self.ayarlar.chunk, exception_on_overflow=False)
                        self._frames.append(data)
                        self._durum.frame_sayisi = len(self._frames)
                    except Exception as e:
                        self._durum.mesaj = f"Kayıt hatası: {str(e)}"
                        self._durum.aktif = False
                        break

                # Kısa bir bekleme (CPU kullanımını azaltır)
                time.sleep(0.001)

        except Exception as e:
            with self._lock:
                self._durum.mesaj = f"Thread hatası: {str(e)}"
                self._durum.aktif = False

    def kaydet(self, dosya_adi: Optional[str] = None) -> Tuple[bool, Optional[str]]:
        """Kaydedilen veriyi dosyaya yazar"""
        with self._lock:
            if not self._frames:
                self._durum.mesaj = "Kaydedilecek veri yok!"
                return False, None

            # Dosya adı oluştur
            if dosya_adi is None:
                zaman = datetime.now().strftime("%Y%m%d_%H%M%S")
                dosya_adi = f"kayit_{zaman}.wav"

            # .wav uzantısı ekle
            if not dosya_adi.endswith('.wav'):
                dosya_adi += '.wav'

            # Kayıtlar klasörü oluştur
            kayitlar_klasoru = "kayitlar"
            if not os.path.exists(kayitlar_klasoru):
                os.makedirs(kayitlar_klasoru)

            dosya_yolu = os.path.join(kayitlar_klasoru, dosya_adi)

            try:
                with wave.open(dosya_yolu, 'wb') as wf:
                    wf.setnchannels(self.ayarlar.channels)
                    wf.setsampwidth(self._audio.get_sample_size(self.ayarlar.format) if self._audio else 2)
                    wf.setframerate(self.ayarlar.sample_rate)
                    wf.writeframes(b''.join(self._frames))

                self._durum.mesaj = f"Kayıt kaydedildi: {dosya_yolu}"
                return True, dosya_yolu

            except Exception as e:
                self._durum.mesaj = f"Dosya kaydetme hatası: {str(e)}"
                return False, None

    def _temizle(self) -> None:
        """Kaynakları temizler (lock içinde çağrılmalı)"""
        try:
            if self._stream:
                self._stream.stop_stream()
                self._stream.close()
                self._stream = None

            if self._audio:
                self._audio.terminate()
                self._audio = None
        except:
            pass

    def get_durum(self) -> KayitDurumu:
        """Kayıt durumunu döndürür"""
        with self._lock:
            # Süreyi güncelle
            if self._durum.aktif:
                self._durum.guncelle_sure()
                self._durum.frame_sayisi = len(self._frames)
                self._durum.mesaj = f"Kayıt devam ediyor - Süre: {self._durum.sure:.1f} saniye"

            # Durum nesnesinin bir kopyasını döndür
            return KayitDurumu(
                aktif=self._durum.aktif,
                sure=self._durum.sure,
                frame_sayisi=self._durum.frame_sayisi,
                mesaj=self._durum.mesaj,
                baslangic_zamani=self._durum.baslangic_zamani
            )

    def get_kayit_listesi(self) -> List[KayitDosyasi]:
        """Kayıtlar klasöründeki dosyaları listeler"""
        kayitlar_klasoru = "kayitlar"
        if not os.path.exists(kayitlar_klasoru):
            return []

        dosyalar = []
        for dosya in os.listdir(kayitlar_klasoru):
            if dosya.endswith('.wav'):
                dosya_yolu = os.path.join(kayitlar_klasoru, dosya)
                try:
                    dosya_boyutu = os.path.getsize(dosya_yolu)
                    dosya_tarihi = datetime.fromtimestamp(os.path.getmtime(dosya_yolu))

                    kayit_dosyasi = KayitDosyasi(
                        ad=dosya,
                        yol=dosya_yolu,
                        boyut=dosya_boyutu,
                        tarih=dosya_tarihi
                    )
                    dosyalar.append(kayit_dosyasi)
                except OSError:
                    # Dosya erişim hatası, atla
                    continue

        # Tarihe göre sırala (en yeni önce)
        dosyalar.sort(key=lambda x: x.tarih, reverse=True)
        return dosyalar

    def ayarlari_guncelle(self,
                          sample_rate: Optional[int] = None,
                          channels: Optional[int] = None,
                          chunk: Optional[int] = None) -> bool:
        """Ses ayarlarını günceller (sadece kayıt dururken)"""
        with self._lock:
            if self._durum.aktif:
                self._durum.mesaj = "Ayarlar kayıt sırasında değiştirilemez!"
                return False

            try:
                # Yeni ayarlar oluştur
                yeni_ayarlar = SesAyarlari(
                    sample_rate=sample_rate or self.ayarlar.sample_rate,
                    channels=channels or self.ayarlar.channels,
                    chunk=chunk or self.ayarlar.chunk
                )

                self.ayarlar = yeni_ayarlar
                self._durum.mesaj = "Ayarlar güncellendi!"
                return True

            except ValueError as e:
                self._durum.mesaj = f"Geçersiz ayar: {str(e)}"
                return False

    def get_ses_ayarlari(self) -> Dict[str, Any]:
        """Mevcut ses ayarlarını döndürür"""
        return {
            'sample_rate': self.ayarlar.sample_rate,
            'channels': self.ayarlar.channels,
            'chunk': self.ayarlar.chunk,
            'format': self.ayarlar.format,
            'channels_str': 'Mono' if self.ayarlar.channels == 1 else 'Stereo'
        }

    def __del__(self):
        """Nesne silinirken kaynakları temizle"""
        if hasattr(self, '_durum') and self._durum.aktif:
            self.kayit_durdur()
        if hasattr(self, '_lock'):
            with self._lock:
                self._temizle()


# Test fonksiyonu
if __name__ == "__main__":
    print("=== Dataclass Tabanlı Ses Kaydedici Test ===")

    # Özel ayarlarla kaydedici oluştur
    ozel_ayarlar = SesAyarlari(
        sample_rate=22050,
        channels=1,
        chunk=512
    )

    kaydedici = SesKaydedici(ayarlar=ozel_ayarlar)

    print(f"Ses ayarları: {kaydedici.get_ses_ayarlari()}")

    print("\nKayıt başlatılıyor...")
    if kaydedici.kayit_baslat():
        print("Kayıt başladı! 3 saniye beklenecek...")

        for i in range(3):
            time.sleep(1)
            durum = kaydedici.get_durum()
            print(f"Durum: {durum.mesaj} | Frame: {durum.frame_sayisi}")

        print("\nKayıt durduruluyor...")
        kaydedici.kayit_durdur()

        print("Kayıt dosyaya kaydediliyor...")
        basarili, dosya_yolu = kaydedici.kaydet("dataclass_test.wav")

        if basarili:
            print(f"✅ Başarılı! Dosya: {dosya_yolu}")

            # Kayıt listesini göster
            print("\n📁 Kayıt listesi:")
            for kayit in kaydedici.get_kayit_listesi():
                print(f"  - {kayit.ad} ({kayit.boyut_kb():.1f} KB, {kayit.tarih})")
        else:
            durum = kaydedici.get_durum()
            print(f"❌ Kayıt başarısız: {durum.mesaj}")

    else:
        durum = kaydedici.get_durum()
        print(f"❌ Kayıt başlatılamadı: {durum.mesaj}")

    print("\n=== Test tamamlandı ===")

def get_files():
    if os.path.exists(folder_path):
        file_paths = glob.glob(os.path.join(folder_path, "*"))
        file_names = [os.path.basename(path) for path in file_paths]
        return file_names
    else:
        return []