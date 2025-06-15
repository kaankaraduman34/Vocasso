import sounddevice as sd
import wave
import threading
import time
import numpy as np
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
    dtype: str = 'int16'
    device: Optional[int] = None  # None = varsayılan mikrofon

    def __post_init__(self):
        """Dataclass oluşturulduktan sonra çağrılır"""
        self.validate()

    def validate(self) -> None:
        """Ayarları doğrular"""
        if self.sample_rate not in [8000, 16000, 22050, 44100, 48000, 96000]:
            raise ValueError(f"Geçersiz sample_rate: {self.sample_rate}")

        if self.channels not in [1, 2]:
            raise ValueError(f"Geçersiz channels: {self.channels}")

        if self.dtype not in ['int16', 'int32', 'float32', 'float64']:
            raise ValueError(f"Geçersiz dtype: {self.dtype}")


@dataclass
class SesKaydedici:
    """
    Sounddevice tabanlı kontrol edilebilir ses kayıt sınıfı
    """
    # Ses ayarları
    ayarlar: SesAyarlari = field(default_factory=SesAyarlari)

    # Private alanlar (post_init'te initialize edilir)
    _durum: KayitDurumu = field(default_factory=KayitDurumu, init=False)
    _kayit_verisi: List[np.ndarray] = field(default_factory=list, init=False)
    _kayit_thread: Optional[threading.Thread] = field(default=None, init=False)
    _lock: threading.Lock = field(default_factory=threading.Lock, init=False)
    _durdur_bayragi: threading.Event = field(default_factory=threading.Event, init=False)

    def __post_init__(self):
        """Dataclass oluşturulduktan sonra çağrılır"""
        self._durum.mesaj = "Kayıt için hazır"
        # Mevcut ses cihazlarını kontrol et
        try:
            devices = sd.query_devices()
            input_devices = [d for d in devices if d['max_input_channels'] > 0]
            if not input_devices:
                self._durum.mesaj = "Giriş cihazı bulunamadı!"
        except Exception as e:
            self._durum.mesaj = f"Ses cihazları kontrol edilemedi: {str(e)}"

    @property
    def kayit_devam_ediyor(self) -> bool:
        """Thread-safe kayıt durumu kontrolü"""
        with self._lock:
            return self._durum.aktif

    @property
    def frame_sayisi(self) -> int:
        """Thread-safe frame sayısı"""
        with self._lock:
            return len(self._kayit_verisi)

    def kayit_baslat(self) -> bool:
        """Kayıt başlatır"""
        with self._lock:
            if self._durum.aktif:
                self._durum.mesaj = "Kayıt zaten devam ediyor!"
                return False

            try:
                # Mikrofon cihazlarını kontrol et
                devices = sd.query_devices()
                input_devices = [d for d in devices if d['max_input_channels'] > 0]

                if not input_devices:
                    self._durum.mesaj = "Mikrofon bulunamadı!"
                    return False

                # Varsayılan giriş cihazını al
                if self.ayarlar.device is None:
                    self.ayarlar.device = sd.default.device[0]  # Varsayılan giriş cihazı

                # Kayıt durumunu aktif et
                self._durum.aktif = True
                self._durum.baslangic_zamani = time.time()
                self._durum.frame_sayisi = 0
                self._kayit_verisi.clear()
                self._durdur_bayragi.clear()

                # Kayıt thread'ini başlat
                self._kayit_thread = threading.Thread(target=self._kayit_dongusu)
                self._kayit_thread.daemon = True
                self._kayit_thread.start()

                self._durum.mesaj = "Kayıt başlatıldı!"
                return True

            except Exception as e:
                self._durum.mesaj = f"Kayıt başlatılamadı: {str(e)}"
                self._durum.aktif = False
                return False

    def kayit_durdur(self) -> bool:
        """Kayıt durdurur"""
        with self._lock:
            if not self._durum.aktif:
                self._durum.mesaj = "Kayıt zaten durmuş!"
                return False

            self._durum.aktif = False
            self._durum.mesaj = "Kayıt durduruluyor..."
            self._durdur_bayragi.set()

        # Thread'in bitmesini bekle (lock dışında)
        if self._kayit_thread and self._kayit_thread.is_alive():
            self._kayit_thread.join(timeout=3)

        with self._lock:
            self._durum.mesaj = "Kayıt durduruldu!"
            return True

    def _kayit_dongusu(self) -> None:
        """Kayıt döngüsü (thread içinde çalışır)"""
        try:
            # Her seferinde 0.1 saniye kayıt al
            duration = 0.1

            while not self._durdur_bayragi.is_set():
                try:
                    # Ses verisi kaydet
                    audio_data = sd.rec(
                        int(duration * self.ayarlar.sample_rate),
                        samplerate=self.ayarlar.sample_rate,
                        channels=self.ayarlar.channels,
                        dtype=self.ayarlar.dtype,
                        device=self.ayarlar.device
                    )

                    # Kaydın tamamlanmasını bekle
                    sd.wait()

                    with self._lock:
                        if not self._durum.aktif:
                            break

                        self._kayit_verisi.append(audio_data)
                        self._durum.frame_sayisi = len(self._kayit_verisi)

                except Exception as e:
                    with self._lock:
                        self._durum.mesaj = f"Kayıt hatası: {str(e)}"
                        self._durum.aktif = False
                        break

        except Exception as e:
            with self._lock:
                self._durum.mesaj = f"Thread hatası: {str(e)}"
                self._durum.aktif = False

    def kaydet(self, dosya_adi: Optional[str] = None) -> Tuple[bool, Optional[str]]:
        """Kaydedilen veriyi dosyaya yazar"""
        with self._lock:
            if not self._kayit_verisi:
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
                # Tüm kayıt verilerini birleştir
                if self._kayit_verisi:
                    tum_veri = np.concatenate(self._kayit_verisi, axis=0)

                    # Soundfile kullanmak yerine wave modülü ile kaydet
                    with wave.open(dosya_yolu, 'wb') as wf:
                        wf.setnchannels(self.ayarlar.channels)

                        # Dtype'a göre sample width belirle
                        if self.ayarlar.dtype == 'int16':
                            wf.setsampwidth(2)
                            # Float verisini int16'ya dönüştür
                            if tum_veri.dtype != np.int16:
                                tum_veri = (tum_veri * 32767).astype(np.int16)
                        elif self.ayarlar.dtype == 'int32':
                            wf.setsampwidth(4)
                            if tum_veri.dtype != np.int32:
                                tum_veri = (tum_veri * 2147483647).astype(np.int32)
                        else:
                            # Float için int16'ya dönüştür
                            wf.setsampwidth(2)
                            tum_veri = (tum_veri * 32767).astype(np.int16)

                        wf.setframerate(self.ayarlar.sample_rate)
                        wf.writeframes(tum_veri.tobytes())

                self._durum.mesaj = f"Kayıt kaydedildi: {dosya_yolu}"
                return True, dosya_yolu

            except Exception as e:
                self._durum.mesaj = f"Dosya kaydetme hatası: {str(e)}"
                return False, None

    def get_durum(self) -> KayitDurumu:
        """Kayıt durumunu döndürür"""
        with self._lock:
            # Süreyi güncelle
            if self._durum.aktif:
                self._durum.guncelle_sure()
                self._durum.frame_sayisi = len(self._kayit_verisi)
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
                          dtype: Optional[str] = None,
                          device: Optional[int] = None) -> bool:
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
                    dtype=dtype or self.ayarlar.dtype,
                    device=device if device is not None else self.ayarlar.device
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
            'dtype': self.ayarlar.dtype,
            'device': self.ayarlar.device,
            'channels_str': 'Mono' if self.ayarlar.channels == 1 else 'Stereo'
        }

    def get_ses_cihazlari(self) -> List[Dict[str, Any]]:
        """Mevcut ses giriş cihazlarını listeler"""
        try:
            devices = sd.query_devices()
            input_devices = []

            for i, device in enumerate(devices):
                if device['max_input_channels'] > 0:
                    input_devices.append({
                        'index': i,
                        'name': device['name'],
                        'channels': device['max_input_channels'],
                        'sample_rate': device['default_samplerate']
                    })

            return input_devices
        except Exception as e:
            return [{'error': f"Cihazlar listelenemedi: {str(e)}"}]

    def __del__(self):
        """Nesne silinirken kaynakları temizle"""
        if hasattr(self, '_durum') and self._durum.aktif:
            self.kayit_durdur()


# Test fonksiyonu
if __name__ == "__main__":
    print("=== Sounddevice Tabanlı Ses Kaydedici Test ===")

    # Mevcut ses cihazlarını listele
    print("\n🎤 Mevcut ses giriş cihazları:")
    try:
        devices = sd.query_devices()
        for i, device in enumerate(devices):
            if device['max_input_channels'] > 0:
                print(f"  {i}: {device['name']} ({device['max_input_channels']} kanal)")
    except Exception as e:
        print(f"  Hata: {e}")

    # Özel ayarlarla kaydedici oluştur
    ozel_ayarlar = SesAyarlari(
        sample_rate=22050,
        channels=1,
        dtype='int16'
    )

    kaydedici = SesKaydedici(ayarlar=ozel_ayarlar)

    print(f"\n📊 Ses ayarları: {kaydedici.get_ses_ayarlari()}")

    print("\n🔴 Kayıt başlatılıyor...")
    if kaydedici.kayit_baslat():
        print("Kayıt başladı! 3 saniye beklenecek...")

        for i in range(3):
            time.sleep(1)
            durum = kaydedici.get_durum()
            print(f"⏱️  Durum: {durum.mesaj} | Frame: {durum.frame_sayisi}")

        print("\n⏹️  Kayıt durduruluyor...")
        kaydedici.kayit_durdur()

        print("💾 Kayıt dosyaya kaydediliyor...")
        basarili, dosya_yolu = kaydedici.kaydet("sounddevice_test.wav")

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

    print("\n✨ Test tamamlandı ===")


def get_files():
    """Kayıtlar klasöründeki dosyaları listeler"""
    if os.path.exists(folder_path):
        file_paths = glob.glob(os.path.join(folder_path, "*"))
        file_names = [os.path.basename(path) for path in file_paths]
        return file_names
    else:
        return []