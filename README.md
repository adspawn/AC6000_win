# ac6000bt-to-pc

ACETECH AC6000MKIII BT の弾速を Python / BLE だけで取得するツールです（**Windows 10/11** 向け。macOS でも利用可）。

## 必要環境

- **Windows 10/11**（Bluetooth 対応）
- Python 3.11+
- Bluetooth 有効
- クロノ電源 ON

## セットアップ（Windows）

1. [Python 3.11+](https://www.python.org/downloads/) をインストール（**Add python.exe to PATH** にチェック）
2. リポジトリフォルダで **`setup.bat`** をダブルクリック

手動で行う場合:

```bat
cd ac6000bt-to-pc
py -3 -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
```

## 実行（Windows）

| バッチ | 内容 |
|--------|------|
| **`run.bat`** | 待受開始（`Ctrl+C` で終了） |
| **`run_speak.bat`** | 待受 + 弾速の音声読み上げ |
| **`run.bat scan`** | 周辺 BLE 一覧（接続先確認） |

コマンドラインから:

```bat
.venv\Scripts\activate
python bind_init.py --listen-forever
```

音声読み上げ:

```bat
python bind_init.py --listen-forever --speak
```

成功時の表示例:

```text
🎯 61.4 メートル毎秒
```

## 接続先アドレス（Windows）

Windows ではデバイスアドレスは **MAC 形式**（例 `AA:BB:CC:DD:EE:FF`）です。

1. `run.bat scan` で ★ 付きの ACETECH 候補のアドレスを確認
2. `config.py` の `DEVICE_ADDRESS` にそのアドレスを書く  
   またはコマンドプロンプトで `set CHRONO_ADDRESS=AA:BB:CC:DD:EE:FF` してから `run.bat`

macOS でコピーした UUID 形式のアドレスは Windows では使えません。

## オプション

| オプション | 説明 |
|-----------|------|
| `--listen-forever` | Ctrl+C まで待受 |
| `--listen-seconds N` | 待受秒数を指定 |
| `--key-p1 147 --key-p2 5` | READ_KEY バイトを手動指定 |
| `--skip-post-init` | READ_KEY のみ送信 |
| `--speak` | 数値を音声読み上げ（Windows: SAPI / macOS: `say`） |

## ファイル構成

| ファイル | 説明 |
|---------|------|
| `setup.bat` / `run.bat` / `run_speak.bat` | Windows 用セットアップ・実行 |
| `bind_init.py` | 接続・初期化・待受・測定値表示 |
| `speech.py` | 数値読み上げ（`--speak` 時） |
| `acetech_protocol.py` | パケット生成と通知解析 |
| `discover.py` | デバイス探索・GATT 調査 |
| `scan.py` | 周辺 BLE 一覧 |
| `config.py` | UUID・アドレスなどの設定 |

## トラブルシュート（Windows）

- デバイスが見つからない → `run.bat scan` で確認
- Python がない → `setup.bat` の案内に従い PATH 付きで再インストール
- 測定値が来ない → `run.bat` で十分待ってから実射。`--listen-forever` 推奨
- 途中切断 → Windows の Bluetooth をオフ/オン、クロノ再起動
- 初回だけ接続できない → 設定 → Bluetooth でクロノを一度ペアリング

## macOS で使う場合

```bash
python3.11 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python bind_init.py --listen-forever
```

`config.py` の既定アドレスは macOS 用 UUID です。`--speak` は `say` コマンドを使用します。

## 注意

メーカー公式の BLE プロトコル仕様は公開されていません。非公式解析に基づく実装です。
