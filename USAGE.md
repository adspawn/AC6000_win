# クイックスタート（Windows）

## 初回

1. **`setup.bat`** を実行
2. クロノ電源 ON
3. （任意）**`run.bat scan`** でアドレスを確認し、`config.py` の `DEVICE_ADDRESS` に設定

## 通常運用

**`run.bat`** をダブルクリック → BB を撃つと `🎯 XX.X メートル毎秒` が表示されます。

音声も欲しい場合は **`run_speak.bat`**。

終了は **Ctrl+C**。

## コマンドライン

```bat
.venv\Scripts\activate
python bind_init.py --listen-forever
python bind_init.py --listen-forever --speak
python scan.py
```

## macOS

```bash
source .venv/bin/activate
python bind_init.py --listen-forever
```
