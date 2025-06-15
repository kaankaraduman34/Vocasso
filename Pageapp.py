import openai
import streamlit as st
import time
import os
from datetime import datetime
import transcriptor,painter
import sys

# Ses kaydedici modülünü import et
try:
    from recorder import SesKaydedici, SesAyarlari,get_files
except ImportError:
    st.error("❌ recorder.py dosyası bulunamadı! Lütfen aynı klasörde olduğundan emin olun.")
    st.stop()

# Sayfa yapılandırması
st.set_page_config(
    page_title="Vocasso",
    page_icon="📱",
    layout="wide"
)

# Session state ile sayfa durumunu takip et
if 'secili_sayfa' not in st.session_state:
    st.session_state.secili_sayfa = "ana_sayfa"

if 'kaydedici' not in st.session_state:
    st.session_state.kaydedici = SesKaydedici()
    st.session_state.kayit_aktif = False
    st.session_state.son_kayit_dosyasi = None

# Ana başlık

# Sidebar - Butonlar dikey sıralama
st.sidebar.title("🎙️ Vocasso")
st.sidebar.write("---")

# Sidebar butonları - Dikey sıralama
if st.sidebar.button("🏠 ANA SAYFA", use_container_width=True, type="primary"):
    st.session_state.secili_sayfa = "ana_sayfa"

st.sidebar.write("")  # Boşluk

if st.sidebar.button("🎙️ SES KAYIT", use_container_width=True, type="primary"):
    st.session_state.secili_sayfa = "Ses Kayıt"

st.sidebar.write("")  # Boşluk

if st.sidebar.button("🖌️ GÖRSEL ÜRET", use_container_width=True, type="primary"):
    st.session_state.secili_sayfa = "gorsel_uret"

st.sidebar.write("")

if st.sidebar.button("ℹ️ HAKKINDA", use_container_width=True, type="primary"):
    st.session_state.secili_sayfa = "hakkinda"

st.sidebar.write("---")
st.sidebar.caption("💡 Sayfa seçmek için yukarıdaki butonları kullanın")

# Ana içerik alanı
# Seçilen sayfayı göster
if st.session_state.secili_sayfa == "ana_sayfa":
    st.header("🏠 Ana Sayfa")
    st.write("---")




    st.subheader("Hoş Geldiniz!")
    st.write("""
        Bu uygulama ses kayıtlarını alarak bir görsele dönüştürme amacıyla tasarlanmıştır.
        """)



    st.info("💡 İpucu: Sol taraftaki 'Ses kayıt' butonuna tıklayarak sesinizi kaydedin. Ardından Görsel üretmek için 'Görsel Üret' sayfasından ses kaydını seçerek ilerleyin!'")

elif st.session_state.secili_sayfa == "Ses Kayıt":
    col1, col2 = st.columns([3, 2])

    with col1:
        st.header("🎛️ Kayıt Kontrolleri")
        mevcut_ayarlar = st.session_state.kaydedici.get_ses_ayarlari()

        st.subheader("📊 Aktif Ayarlar")
        st.info(f"""
            🔊 **Sample Rate:** {mevcut_ayarlar['sample_rate']} Hz  
            🎚️ **Kanal:** {mevcut_ayarlar['channels_str']}  
            """)
        with st.expander("🔧 Ses Ayarlarını Değiştir"):
            st.write("**Ses Kalitesi Ayarları**")

            sample_rate = st.selectbox(
                "Örnekleme Hızı (Hz)",
                [8000, 16000, 22050, 44100, 48000, 96000],
                index=[8000, 16000, 22050, 44100, 48000, 96000].index(mevcut_ayarlar['sample_rate']),
                help="Yüksek değer = Daha iyi kalite, Daha büyük dosya"
            )

            channels = st.selectbox(
                "Kanal Sayısı",
                [1, 2],
                format_func=lambda x: "Mono (Tek kanal)" if x == 1 else "Stereo (Çift kanal)",
                index=mevcut_ayarlar['channels'] - 1
            )



            # Ayarları uygula
            if st.button("🔄 Ayarları Uygula", use_container_width=True):
                if not st.session_state.kayit_aktif:
                    if st.session_state.kaydedici.ayarlari_guncelle(
                            sample_rate=sample_rate,
                            channels=channels,
                            dtype='float32'
                    ):
                        st.success("✅ Ayarlar güncellendi!")
                        st.rerun()
                    else:
                        durum = st.session_state.kaydedici.get_durum()
                        st.error(f"❌ Hata: {durum.mesaj}")
                else:
                    st.warning("⚠️ Önce kaydı durdurun!")

        # Kayıt butonları
        col_basla, col_dur = st.columns(2)

        with col_basla:
            if st.button("🎙️ KAYIT BAŞLAT",
                         disabled=st.session_state.kayit_aktif,
                         type="primary",
                         use_container_width=True):

                if st.session_state.kaydedici.kayit_baslat():
                    st.session_state.kayit_aktif = True
                    st.success("✅ Kayıt başlatıldı!")
                    st.rerun()
                else:
                    durum = st.session_state.kaydedici.get_durum()
                    st.error(f"❌ Kayıt başlatılamadı: {durum.mesaj}")

        with col_dur:
            if st.button("⏹️ KAYIT DURDUR",
                         disabled=not st.session_state.kayit_aktif,
                         type="secondary",
                         use_container_width=True):

                if st.session_state.kaydedici.kayit_durdur():
                    st.session_state.kayit_aktif = False
                    st.success("✅ Kayıt durduruldu!")
                    st.rerun()
                else:
                    st.error("❌ Kayıt durdurulamadı!")

        # Kayıt durumu gösterimi
        st.markdown("### 📊 Anlık Durum")
        durum = st.session_state.kaydedici.get_durum()

        if durum.aktif:
            st.success("🔴 **KAYIT DEVAM EDİYOR**")

            # Metrikleri yan yana göster
            metric_col1, metric_col2 = st.columns(2)
            with metric_col1:
                st.metric("⏰ Süre", f"{durum.sure:.1f} saniye")
            with metric_col2:
                st.metric("📊 Frame", durum.frame_sayisi)

            # İlerleme çubuğu (sanal)
            progress_value = min(durum.sure / 60.0, 1.0)  # 60 saniye max için
            st.progress(progress_value)

        else:
            st.info("⚫ Kayıt bekleniyor...")

        # Durum mesajı
        if durum.mesaj:
            st.write(f"**📝 Durum:** {durum.mesaj}")

    with col2:
        st.header("💾 Kaydet & Yönet")

        # Kaydetme bölümü
        if st.session_state.kaydedici.frame_sayisi > 0 and not st.session_state.kayit_aktif:

            st.markdown("#### 📝 Dosya Adı Belirleme")

            # Dosya adı türü seçimi
            dosya_tipi = st.radio(
                "Kayıt nasıl adlandırılsın?",
                ["🎯 Özel Ad", "🤖 Otomatik Ad"],
                horizontal=True
            )

            if dosya_tipi == "🎯 Özel Ad":
                # Özel dosya adı girişi
                ozel_ad = st.text_input(
                    "Dosya adını girin:",
                    placeholder="Örnek: toplanti_kaydi",
                    help="Sadece dosya adını girin. '.wav' otomatik eklenecek.",
                    key="dosya_adi_input"
                )

                if ozel_ad and ozel_ad.strip():
                    dosya_adi = ozel_ad.strip()
                    # Geçersiz karakterleri temizle
                    import re

                    dosya_adi = re.sub(r'[<>:"/\\|?*]', '_', dosya_adi)
                else:
                    # Boşsa otomatik ad kullan
                    zaman = datetime.now().strftime("%Y%m%d_%H%M%S")
                    dosya_adi = f"kayit_{zaman}"
                    if not ozel_ad:  # Hiç girilmemişse uyarı verme
                        pass
                    else:  # Boş girilmişse uyarı ver
                        st.warning("⚠️ Boş ad! Otomatik ad kullanılacak.")
            else:
                # Otomatik ad oluştur
                zaman = datetime.now().strftime("%Y%m%d_%H%M%S")
                dosya_adi = f"voice_draw_{zaman}"

            # Önizleme göster
            final_dosya_adi = dosya_adi if dosya_adi.endswith('.wav') else f"{dosya_adi}.wav"
            st.info(f"📄 **Kaydedilecek:** `{final_dosya_adi}`")

            # Kaydet butonu
            if st.button("💾 KAYDET", type="primary", use_container_width=True, key="kaydet_btn"):
                with st.spinner("Kaydediliyor..."):
                    basarili, dosya_yolu = st.session_state.kaydedici.kaydet(dosya_adi)

                    if basarili:
                        st.session_state.son_kayit_dosyasi = dosya_yolu
                        st.success(f"✅ Başarıyla kaydedildi!")
                        st.success(f"📁 **Konum:** `{dosya_yolu}`")

                        # Dosya bilgilerini göster
                        if os.path.exists(dosya_yolu):
                            dosya_boyutu = os.path.getsize(dosya_yolu)
                            st.metric("📊 Dosya Boyutu", f"{dosya_boyutu / 1024:.1f} KB")

                        time.sleep(1)  # Kısa bir bekleme
                        st.rerun()
                    else:
                        durum = st.session_state.kaydedici.get_durum()
                        st.error(f"❌ Kaydetme hatası: {durum.mesaj}")

        elif st.session_state.kayit_aktif:
            st.info("⏳ Kayıt devam ediyor... Önce kaydı durdurun.")
        else:
            st.info("🎤 Henüz kayıt yapılmadı. Kayıt başlatın!")

    # Kayıtlar listesi (tam genişlik)
    st.markdown("---")
    st.header("📁 Kayıtlar Arşivi")

    # Kayıtları listele
    kayitlar = st.session_state.kaydedici.get_kayit_listesi()

    if kayitlar:
        st.write(f"📊 **Toplam {len(kayitlar)} kayıt bulundu**")

        # Kayıtları tablo şeklinde göster
        for i, kayit in enumerate(kayitlar):
            # Her kayıt için bir container
            with st.container():
                kayit_col1, kayit_col2, kayit_col3, kayit_col4,kayit_col5 = st.columns([3, 2, 1, 2,2])

                with kayit_col1:
                    # Son kayıt işareti
                    if (st.session_state.son_kayit_dosyasi and
                            kayit.yol == st.session_state.son_kayit_dosyasi):
                        st.markdown(f"🆕 **{kayit.ad}** *(Yeni)*")
                    else:
                        st.markdown(f"🎵 **{kayit.ad}**")

                with kayit_col2:
                    st.write(f"📅 {kayit.tarih.strftime('%d/%m/%Y %H:%M')}")

                with kayit_col3:
                    st.write(f"📊 {kayit.boyut_kb():.1f} KB")

                with kayit_col5:
                    # İndirme butonu
                    if os.path.exists(kayit.yol):
                        with open(kayit.yol, 'rb') as dosya:
                            st.download_button(
                                label="⬇️ İndir",
                                data=dosya.read(),
                                file_name=kayit.ad,
                                mime="audio/wav",
                                key=f"indir_{i}",
                                use_container_width=True
                            )
                    else:
                        st.error("❌ Dosya bulunamadı")

                with kayit_col4:
                    st.audio(data=kayit.yol)

            # Ayırıcı (son kayıt hariç)
            if i < len(kayitlar) - 1:
                st.divider()

    else:
        st.info("📂 Henüz hiç kayıt yapılmamış. İlk kaydınızı oluşturun!")

elif st.session_state.secili_sayfa == "gorsel_uret":

    col1, col2, col3 = st.columns([1, 1, 1])

    with col1:
        st.header("🔄 API Ayarları")
        with st.expander("API Anahtarlarınızı girin"):

            if 'saved_openai' not in st.session_state:
                st.session_state.saved_openai = None

            openai_key = st.text_input(
                "OpenAI API Key",
                value=st.session_state.saved_openai,  # Kaydedilmiş değeri göster
                placeholder="sk-... formatında API anahtarınızı girin",
                type="password",
                key="openai_input"
            )

            kaydet = st.button("Kaydet")
            if kaydet:
                if openai_key != None:
                    if openai_key.strip():
                        st.session_state.saved_openai = openai_key
                        st.session_state.transcriptor_client= transcriptor.set_OpenAI_api_key(st.session_state.saved_openai)
                        st.session_state.painter_client = painter.set_OpenAI_api_key(st.session_state.saved_openai)


                    st.success("✅ API Anahtarları kaydedildi!")
                else:
                    st.error("❗ API Anahtarı boş bırakılamaz!")



    st.write("---")

    file_names = get_files()

    col1 , col2,col3 = st.columns([1,1,2])
    with col1:
        st.markdown("""
                    <style>
                    .big-font {
                        font-size:20px !important;
                    }
                    </style>
                    """, unsafe_allow_html=True)
        st.markdown('<p class="big-font">Ses kaydını seç</p>', unsafe_allow_html=True)
        selected_index = st.selectbox(
            "Sesi dinle",
            range(len(file_names)),
            format_func=lambda i: file_names[i],
            label_visibility="hidden",
            index=None
        )


    with col2:

        if (selected_index !=None) and len(file_names) > 0:

            st.markdown("""
            <style>
            .big-font {
                font-size:20px !important;
            }
            </style>
            """, unsafe_allow_html=True)
            st.markdown('<p class="big-font">Sesi dinle</p>', unsafe_allow_html=True)
            st.write("")
            st.write("")
            st.session_state.file_path = "kayitlar/"+  file_names[selected_index]
            st.audio(data= st.session_state.file_path)
        elif len(file_names) > 0:
            st.markdown("""
                                    <style>
                                    .big-font {
                                        font-size:20px !important;
                                    }
                                    </style>
                                    """, unsafe_allow_html=True)
            st.markdown('<p class="big-font">Ses seçilmedi.</p>', unsafe_allow_html=True)
        else:
            st.markdown("""
                        <style>
                        .big-font {
                            font-size:20px !important;
                        }
                        </style>
                        """, unsafe_allow_html=True)
            st.markdown('<p class="big-font">Ses Kaydı Bulunamadı.</p>', unsafe_allow_html=True)

    st.write("---")
    def check_available():
        return (selected_index == None) or (openai_key == None)

    if check_available():

        st.info("Görsel Üretmek için API Anahtarınızı girdiğinizden ve ses kaydını seçtiğinizden emin olun!",)
    gorsel_uret = st.button("Görsel Üret",disabled=check_available())



    if gorsel_uret:
        try:
            with st.spinner("Ses transkript ediliyor..",show_time=True):
                st.session_state.voice_prompt = transcriptor.transcribe(st.session_state.file_path,languages="tr",client=st.session_state.transcriptor_client)

            with st.spinner("Görsel Üretiliyor..", show_time=True):
                st.session_state.image_path = painter.generate_image(st.session_state.voice_prompt,client=st.session_state.painter_client)
                st.image(st.session_state.image_path)
            st.write(st.session_state.voice_prompt)
        except openai.AuthenticationError:
            st.error("❗OpenAI Key Hatalı!")

    st.write("---")

elif st.session_state.secili_sayfa == "hakkinda":
    st.header("ℹ️ Hakkında")
    st.write("---")

    col1, col2 = st.columns([2, 1])

    with col1:
        st.subheader("Bu Uygulama Hakkında")
        st.write("""
        
        ### 🛠️ Özellikler
        - **Gelişmiş Ses Kayıt**: Ses kayıt menüsünde özelleştirilebilen kayıt ayarları.
        - **İsimlentirilebilen kayıt dosyaları**: Otomatik ya da isimlendirilebilen ses kayıtları
        - **Kayıt dinleme**: Seçilen kayıtları dinleme
        - **Kayıtları listeleme**: Daha önceden kaydedilen kayıtları görüntüleme
        - **Görsel üretimi**: Kayda göre zenginleştirilmiş görsel üretimi

        ### 🚀 Teknolojiler
        - Python
        - Streamlit
        - OpenAI
        """)

        st.subheader("İletişim")
        with st.form("iletisim_formu"):
            isim = st.text_input("İsim")
            email = st.text_input("E-posta")
            mesaj = st.text_area("Mesaj")

            if st.form_submit_button("Gönder"):
                if isim and email and mesaj:
                    st.success(f"Teşekkürler {isim}! Mesajınız alınmıştır.")
                else:
                    st.error("Lütfen tüm alanları doldurun.")

    with col2:
        st.subheader("📊 Uygulama Bilgileri")

        st.metric("Streamlit Sürümü", f"{st.__version__}")
        st.metric("Python Sürümü", f"{sys.version_info.major}.{sys.version_info.minor}")
        st.metric("OpenAI Sürümü",f"{openai.__version__}")
        st.metric("Toplam Sayfa", "4")

        st.write("---")

        st.subheader("🔗 Faydalı Linkler")
        st.write("""
        - [Streamlit Dokümantasyonu](https://docs.streamlit.io)
        - [Python.org](https://python.org)
        - [OpenAI Dökümantasyonu](https://platform.openai.com/docs/api-reference/introduction)
        """)

if st.session_state.kayit_aktif:
    # Footer'da yenileme göstergesi
    st.markdown("---")
    st.markdown(
        '<div style="text-align: center; color: #ff4444;"> \
        🔴 Canlı yayın - Otomatik yenilenme aktif</div>',
        unsafe_allow_html=True
    )
    time.sleep(1)
    st.rerun()


# Footer
st.write("---")
st.caption("📅 2025 | Streamlit Vocasso")
