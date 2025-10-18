from PIL import Image
import os

# Пути к QR кодам
qr_tests_path = r"C:\Users\everg\halyk-hr-forum\static\images\QR_Tests.jpg"
qr_vac_path = r"C:\Users\everg\halyk-hr-forum\static\images\QR_Vac.jpg"

def get_image_size(path):
    if os.path.exists(path):
        with Image.open(path) as img:
            width, height = img.size
            print(f"📁 {os.path.basename(path)}")
            print(f"   Размер: {width}x{height} px")
            print(f"   Соотношение: {width/height:.2f}")
            print()
            return width, height
    else:
        print(f"❌ Файл не найден: {path}")
        return None, None

print("🔍 Проверяем размеры QR кодов:\n")

# Проверяем оба QR кода
tests_w, tests_h = get_image_size(qr_tests_path)
vac_w, vac_h = get_image_size(qr_vac_path)

# Рекомендации
print("💡 Рекомендации для дашборда:")
print(f"   Экран: 1080x1920 (ширина x высота)")
print(f"   25% высоты = {1920 * 0.25:.0f} px")
print(f"   Каждый QR займет примерно: ~400x400 px на экране")