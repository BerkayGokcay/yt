import yt_dlp
import time
import json
from pathlib import Path
from typing import List, Optional, Set
import random
import hashlib

class ChannelSubtitleDownloader:
    def __init__(self, proxy_list: Optional[List[str]] = None, output_dir: str = "subtitles", archive_file: str = "downloaded_archive.txt", cookies_file: Optional[str] = None):
        """
        Kanal bazlı altyazı indirici
        
        Args:
            proxy_list: Proxy listesi (örn: ['http://user:pass@ip:port'])
            output_dir: Altyazıların kaydedileceği klasör
            archive_file: İndirilen videoların ID'lerinin tutulduğu dosya
            cookies_file: YouTube cookies dosyası (Netscape formatı)
        """
        self.proxy_list = proxy_list or []
        self.current_proxy_index = 0
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(exist_ok=True)
        self.archive_file = Path(archive_file)
        self.cookies_file = Path(cookies_file) if cookies_file else None
        self.failed_proxies = set()
        self.download_count = 0
        self.proxy_rotation_threshold = 3
        
        # Cookies dosyası kontrolü
        if self.cookies_file and not self.cookies_file.exists():
            print(f"⚠️ Uyarı: Cookies dosyası bulunamadı: {self.cookies_file}")
            print("💡 Yaş kısıtlamalı videolar için cookies gereklidir")
        
        # Archive dosyasını oluştur
        if not self.archive_file.exists():
            self.archive_file.touch()
    
    def load_downloaded_ids(self) -> Set[str]:
        """İndirilen video ID'lerini yükle"""
        if self.archive_file.exists():
            with open(self.archive_file, 'r', encoding='utf-8') as f:
                return set(line.strip() for line in f if line.strip())
        return set()
    
    def save_downloaded_id(self, video_id: str):
        """İndirilen video ID'sini kaydet"""
        with open(self.archive_file, 'a', encoding='utf-8') as f:
            f.write(f"{video_id}\n")
    
    def get_next_proxy(self) -> Optional[str]:
        """Bir sonraki kullanılabilir proxy'yi döndür"""
        if not self.proxy_list:
            return None
            
        available_proxies = [p for p in self.proxy_list if p not in self.failed_proxies]
        
        if not available_proxies:
            print("⚠️ Tüm proxy'ler başarısız oldu, başarısız listeyi sıfırlıyorum...")
            self.failed_proxies.clear()
            available_proxies = self.proxy_list
            
        self.current_proxy_index = (self.current_proxy_index + 1) % len(available_proxies)
        return available_proxies[self.current_proxy_index]
    
    def get_ydl_opts(self, proxy: Optional[str] = None, for_listing: bool = False) -> dict:
        """yt-dlp ayarlarını oluştur"""
        opts = {
            'quiet': False,
            'no_warnings': False,
            'extract_flat': for_listing,
            'socket_timeout': 30,
            'retries': 10,
            'fragment_retries': 10,
            'file_access_retries': 5,
            'ignoreerrors': True,
            # YouTube rate limit bypass ayarları
            'extractor_args': {
                'youtube': {
                    'player_client': ['android', 'web'],  # Android client kullan
                    'skip': ['dash', 'hls']  # Gereksiz formatları atla
                }
            },
            # User agent değiştir (bot tespitini engelle)
            'http_headers': {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
                'Accept-Language': 'en-us,en;q=0.5',
                'Sec-Fetch-Mode': 'navigate',
            },
        }
        
        # Cookies ekle (varsa)
        if self.cookies_file and self.cookies_file.exists():
            opts['cookiefile'] = str(self.cookies_file)
        
        if not for_listing:
            # Altyazı indirme için ek ayarlar
            opts.update({
                'skip_download': True,
                'writesubtitles': True,
                'writeautomaticsub': True,
                'subtitleslangs': ['tr', 'en'],
                'subtitlesformat': 'srt/best',
                'outtmpl': str(self.output_dir / '%(channel)s/%(title)s [%(id)s].%(ext)s'),
                'ratelimit': None,
                'throttledratelimit': None,
                'concurrent_fragment_downloads': 5,
            })
        
        if proxy:
            opts['proxy'] = proxy
            
        return opts
    
    def get_channel_videos(self, channel_identifier: str, max_videos: int = 30, sort_by: str = 'date') -> List[dict]:
        """
        Kanaldan son N videoyu çek
        
        Args:
            channel_identifier: Kanal adı veya URL
            max_videos: Çekilecek maksimum video sayısı
            sort_by: Sıralama türü ('date' = en yeni, 'popular' = en popüler)
        """
        print(f"\n🔍 Kanal videoları taranıyor: {channel_identifier}")
        print(f"📊 Maksimum video sayısı: {max_videos}")
        print(f"🔢 Sıralama: {sort_by}")
        
        # Kanal URL'ini oluştur
        if channel_identifier.startswith('http'):
            channel_url = channel_identifier
        elif channel_identifier.startswith('@'):
            channel_url = f"https://www.youtube.com/{channel_identifier}/videos"
        else:
            channel_url = f"https://www.youtube.com/@{channel_identifier}/videos"
        
        # Sıralama parametresi ekle
        if sort_by == 'date':
            channel_url += "?sort=dd"  # Sort by date (newest first)
        elif sort_by == 'popular':
            channel_url += "?sort=p"   # Sort by popularity
        
        proxy = self.get_next_proxy() if self.proxy_list else None
        ydl_opts = self.get_ydl_opts(proxy=proxy, for_listing=True)
        ydl_opts['playlistend'] = max_videos  # İlk N videoyu al (en yeni olan N video)
        
        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                print(f"🌐 URL: {channel_url}")
                if proxy:
                    print(f"🔄 Proxy: {proxy}")
                
                info = ydl.extract_info(channel_url, download=False)
                
                if not info:
                    print("❌ Kanal bilgisi alınamadı")
                    return []
                
                entries = info.get('entries', [])
                videos = []
                
                for entry in entries[:max_videos]:
                    if entry:
                        video_info = {
                            'id': entry.get('id'),
                            'title': entry.get('title'),
                            'url': entry.get('url') or f"https://www.youtube.com/watch?v={entry.get('id')}",
                            'channel': info.get('channel') or info.get('uploader'),
                        }
                        videos.append(video_info)
                
                print(f"✅ {len(videos)} video bulundu")
                return videos
                
        except Exception as e:
            print(f"❌ Kanal videoları alınırken hata: {e}")
            return []
    
    def download_subtitles(self, video_info: dict, max_retries: int = 5) -> bool:
        """Tek bir videonun altyazılarını indir"""
        video_id = video_info['id']
        url = video_info['url']
        
        # Daha önce indirilmiş mi kontrol et
        downloaded_ids = self.load_downloaded_ids()
        if video_id in downloaded_ids:
            print(f"⏭️ Atlanıyor (zaten indirilmiş): {video_info['title']}")
            return True
        
        retries = 0
        last_error = None
        
        while retries < max_retries:
            try:
                # ÖNEMLI: İlk denemeden itibaren proxy kullan
                proxy = None
                if self.proxy_list:
                    proxy = self.get_next_proxy()
                
                ydl_opts = self.get_ydl_opts(proxy)
                
                with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                    print(f"\n📥 İndiriliyor: {video_info['title']}")
                    print(f"🆔 Video ID: {video_id}")
                    if proxy:
                        print(f"🔄 Kullanılan Proxy: {proxy[:30]}...")  # Sadece ilk 30 karakter (güvenlik)
                    
                    info = ydl.extract_info(url, download=True)
                    
                    if info:
                        # Başarılı indirmeyi kaydet
                        self.save_downloaded_id(video_id)
                        print(f"✅ Başarılı: {video_info['title']}")
                        self.download_count += 1
                        return True
                        
            except yt_dlp.utils.DownloadError as e:
                error_msg = str(e).lower()
                last_error = str(e)
                
                # 429 veya rate limit tespiti
                if '429' in error_msg or 'too many requests' in error_msg or 'throttl' in error_msg or 'rate limit' in error_msg:
                    print(f"⚠️ Rate Limit Tespit Edildi! (Deneme {retries + 1}/{max_retries})")
                    
                    if self.proxy_list:
                        if proxy:
                            print(f"❌ Proxy başarısız olarak işaretlendi: {proxy[:30]}...")
                            self.failed_proxies.add(proxy)
                        
                        # Yeni proxy al ve tekrar dene
                        retries += 1
                        wait_time = min(5 * (retries), 30)  # Exponential backoff (max 30 saniye)
                        print(f"⏳ {wait_time} saniye bekleyip farklı proxy ile tekrar denenecek...")
                        time.sleep(wait_time)
                        continue
                    else:
                        # Proxy yoksa uzun bekle
                        print("⚠️ Proxy bulunamadı! Uzun bekleme gerekiyor...")
                        wait_time = 60 * (retries + 1)  # 60, 120, 180 saniye...
                        print(f"⏳ {wait_time} saniye bekleniyor...")
                        time.sleep(wait_time)
                        retries += 1
                        continue
                else:
                    print(f"❌ Hata: {e}")
                    retries += 1
                    time.sleep(random.uniform(2, 5))
                    
            except Exception as e:
                last_error = str(e)
                print(f"❌ Beklenmeyen hata: {e}")
                retries += 1
                time.sleep(random.uniform(2, 5))
        
        print(f"💔 Başarısız (maksimum deneme sayısına ulaşıldı): {video_info['title']}")
        if last_error:
            print(f"📝 Son hata: {last_error}")
        return False
    
    def process_channel(self, channel_identifier: str, max_videos: int = 30, delay_between: tuple = (2, 5)):
        """Bir kanalın videolarını işle"""
        print(f"\n{'='*70}")
        print(f"📺 KANAL İŞLENİYOR: {channel_identifier}")
        print(f"{'='*70}")
        
        # Videoları al
        videos = self.get_channel_videos(channel_identifier, max_videos)
        
        if not videos:
            print("⚠️ Video bulunamadı veya kanal erişilemedi")
            return
        
        # İndirme istatistikleri
        total = len(videos)
        successful = 0
        skipped = 0
        failed = 0
        
        print(f"\n🚀 {total} video için altyazı indirme başlıyor...")
        
        for idx, video in enumerate(videos, 1):
            print(f"\n{'='*70}")
            print(f"İlerleme: {idx}/{total}")
            print(f"{'='*70}")
            
            # Daha önce indirilmiş mi kontrol et
            downloaded_ids = self.load_downloaded_ids()
            if video['id'] in downloaded_ids:
                skipped += 1
                print(f"⏭️ Atlanıyor (zaten indirilmiş): {video['title']}")
            else:
                if self.download_subtitles(video):
                    successful += 1
                else:
                    failed += 1
            
            # Son video değilse bekle
            if idx < total:
                wait_time = random.uniform(*delay_between)
                print(f"⏱️ Sonraki video için {wait_time:.1f} saniye bekleniyor...")
                time.sleep(wait_time)
        
        # Özet
        print(f"\n{'='*70}")
        print(f"📊 KANAL ÖZET: {channel_identifier}")
        print(f"{'='*70}")
        print(f"✅ Yeni indirilen: {successful}/{total}")
        print(f"⏭️ Atlandı (zaten var): {skipped}/{total}")
        print(f"❌ Başarısız: {failed}/{total}")
        print(f"📁 Klasör: {self.output_dir.absolute()}")
    
    def process_channels(self, channels: List[str], max_videos_per_channel: int = 30, delay_between_videos: tuple = (2, 5), delay_between_channels: tuple = (5, 10)):
        """Birden fazla kanalı işle"""
        total_channels = len(channels)
        
        print(f"\n{'#'*70}")
        print(f"🎬 TOPLU KANAL İŞLEME BAŞLIYOR")
        print(f"{'#'*70}")
        print(f"📺 Toplam kanal sayısı: {total_channels}")
        print(f"📊 Her kanaldan maksimum video: {max_videos_per_channel}")
        print(f"📁 Çıktı klasörü: {self.output_dir.absolute()}")
        print(f"💾 Archive dosyası: {self.archive_file.absolute()}")
        
        for idx, channel in enumerate(channels, 1):
            print(f"\n\n{'#'*70}")
            print(f"KANAL {idx}/{total_channels}")
            print(f"{'#'*70}")
            
            self.process_channel(channel, max_videos_per_channel, delay_between_videos)
            
            # Son kanal değilse bekle
            if idx < total_channels:
                wait_time = random.uniform(*delay_between_channels)
                print(f"\n⏱️ Sonraki kanal için {wait_time:.1f} saniye bekleniyor...\n")
                time.sleep(wait_time)
        
        # Genel özet
        print(f"\n\n{'#'*70}")
        print(f"🎉 TÜM KANALLAR İŞLENDİ")
        print(f"{'#'*70}")
        print(f"✅ Toplam işlenen kanal: {total_channels}")
        print(f"📁 Altyazılar: {self.output_dir.absolute()}")
        print(f"💾 Archive: {self.archive_file.absolute()}")


# KULLANIM ÖRNEĞİ
if __name__ == "__main__":
    # Proxy listesi
    proxies = [
        # 'http://kullanici1:sifre123@192.168.1.100:8080',
        # 'http://kullanici2:sifre456@192.168.1.101:8080',
        # 'http://kullanici3:sifre789@192.168.1.102:8080',
    ]
    
    # İşlenecek kanallar
    # Format: '@kanaladi' veya 'kanaladi' veya tam URL
    channels = [
        '@TEDx',
        '@Fireship',
        '@ThePrimeTimeagen',
        # Daha fazla kanal ekleyin...
    ]
    
    # İndiriciyi başlat
    downloader = ChannelSubtitleDownloader(
        proxy_list=proxies if proxies else None,
        output_dir="subtitles",
        archive_file="downloaded_archive.txt",
        cookies_file="youtube_cookies.txt"  # Opsiyonel: Yaş kısıtlamalı videolar için
    )
    
    # Kanalları işle
    downloader.process_channels(
        channels=channels,
        max_videos_per_channel=30,  # Her kanaldan son 30 video
        delay_between_videos=(2, 5),  # Videolar arası bekleme
        delay_between_channels=(5, 10)  # Kanallar arası bekleme
    )
    
    # TEK BİR KANAL İÇİN KULLANIM:
    # downloader.process_channel('@kanaladi', max_videos=30)