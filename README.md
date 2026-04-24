# VRChat-AI

VRChat上で動作する日本語AIエージェントです。  
マイクからの音声を認識し、LLMで応答を生成して、音声合成で返答します。  
会話履歴・短期記憶（STM）・長期記憶（LTM）による記憶システムも搭載しています。

---

## 機能一覧

| 機能 | 説明 |
|------|------|
| 🎤 音声認識（STT） | Faster-Whisper によるリアルタイム文字起こし |
| 🧠 AI応答生成 | LiteLLM 経由で任意のLLMに対応（Ollama / OpenAI 等） |
| 🔊 音声合成（TTS） | GPT-SoVITS-v2pro による高品質な日本語合成 |
| 💾 記憶システム | STM（短期記憶）→ LTM（長期記憶）の自動昇格・減衰 |
| 🎮 VRChat連携 | OSC通信によるアバター・チャットボックス連携 |
| 👁️ 視覚認識 | YOLO + OCR による発話者検出・名前認識（オプション） |
| 🗣️ ウェイクワード | 特定のワードを呼びかけたときのみ反応するモード |

---

## ディレクトリ構成

```
VRChat-AI/
│
├── app.py                  # エントリーポイント（ここから起動）
│
├── core/                   # AI・会話・記憶コア
│   ├── talk_ai.py          # メイン会話ループ（音声 / テキスト両対応）
│   ├── memory_system.py    # STM / LTM 記憶システム（SQLite）
│   ├── speak_ai.py         # 音声合成（GPT-SoVITS）
│   └── mic_input.py        # 音声入力・文字起こし（Faster-Whisper）
│
├── vision/                 # VRChat 視覚認識（オプション）
│   └── vrc_person_speaker_listener.py  # YOLO + OCR による発話者検出
│
├── utils/                  # ユーティリティ
│   └── list_devices.py     # オーディオデバイス一覧表示
│
├── data/
│   ├── persona.txt         # AIのキャラクター設定（.sampleを参考に作成）
│   └── memory.db           # 会話ログ・記憶DB（自動生成）
│
├── .env                    # 環境変数設定（.env.exampleを参考に作成）
├── .env.example            # 設定テンプレート
├── requirements.txt        # 依存パッケージ
└── README.md
```

> **統合・削除したファイルについて**  
> - `talk.py` → `core/talk_ai.py` に統合（重複削除）  
> - `vrc_yolo_capture.py` → `vision/vrc_person_speaker_listener.py` に統合（上位版に一本化）

---

## 動作フロー

```
マイク入力
   ↓  (Faster-Whisper)
テキスト変換
   ↓
ウェイクワード判定（任意）
   ↓
LLM へ送信（LiteLLM + Ollama / OpenAI）
   ↓  長期記憶をシステムプロンプトに注入
AI 応答生成
   ↓
GPT-SoVITS で音声合成
   ↓
スピーカー出力（VRChat 上で発話）
   ↓
記憶メンテナンス（STM → LTM 昇格・減衰）
```

---

## セットアップ

### 動作環境

- Windows 11
- Python 3.10 以上
- NVIDIA GPU（CUDA 対応推奨）
- [GPT-SoVITS-v2pro](https://github.com/RVC-Boss/GPT-SoVITS) を別途起動しておくこと
- [MeCab](https://taku910.github.io/mecab/) + ipadic 辞書（記憶システム使用時）
- [Tesseract OCR](https://github.com/UB-Mannheim/tesseract/wiki)（視覚認識使用時）

---

### 手順

#### 1. リポジトリをクローン

```bash
git clone https://github.com/O-TYAN64/VRChat-AI.git
cd VRChat-AI
```

#### 2. 仮想環境を作成（推奨）

```bash
python -m venv venv
venv\Scripts\activate
```

#### 3. 依存パッケージをインストール

```bash
pip install -r requirements.txt
```

> Torch は CUDA バージョンに合わせて別途インストールを推奨します。  
> 例: `pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu121`

#### 4. 環境変数を設定

`.env.example` をコピーして `.env` を作成し、各項目を埋めてください。

```bash
copy .env.example .env
```

主要な設定項目：

```env
# 使用するLLM（Ollamaの場合）
LITELLM_MODEL=deepseek-r1:latest
LITELLM_PROVIDER=ollama

# 音声デバイスのインデックス（utils/list_devices.pyで確認）
AUDIO_INPUT_DEVICE_INDEX=14
AUDIO_OUTPUT_DEVICE_INDEX=16

# STTモデルサイズ（精度とVRAMのトレードオフ）
STT_MODEL_SIZE=large-v3

# GPT-SoVITSのURL・参照音声
GPT_SOVITS_URL=http://127.0.0.1:9874
GPT_SOVITS_REF_AUDIO=ref.wav

# MeCab辞書パス（記憶システム使用時）
MECAB_IPADIC=C:\MeCab\dic\ipadic
```

全項目は [`.env.example`](.env.example) を参照してください。

#### 5. キャラクター設定（任意）

`data/persona.txt.sample` を参考に `data/persona.txt` を作成してください。  
AIのロール・名前・一人称などを自由に設定できます。

```
# Role：
あなたは〇〇です。

# 基本情報
あなたの名前：〇〇
一人称：私 / 俺 / あたし など
```

#### 6. オーディオデバイスの確認

```bash
python utils/list_devices.py
```

表示されたデバイス一覧から `index` 番号を `.env` に設定してください。

#### 7. GPT-SoVITS を起動

別のターミナルで GPT-SoVITS-v2pro を起動しておきます。

#### 8. 起動

```bash
# 音声モード（デフォルト）
python app.py

# テキスト入力モード（マイク不要）
python app.py --text
```

---

## テキストモードのコマンド

テキストモード（`--text`）では以下のコマンドが使えます。

| コマンド | 説明 |
|----------|------|
| `/quit`  | 終了 |
| `/stats` | DB統計（ログ数・STM・LTM件数）を表示 |
| `/ltm`   | 長期記憶の内容を表示 |

---

## 記憶システムについて

会話の内容はSQLiteに保存され、3段階で管理されます。

```
会話ログ（全履歴保存）
    ↓
STM（短期記憶）：単語・文を一時的に保持。一定時間で自動削除。
    ↓ 重みが閾値を超えると昇格
LTM（長期記憶）：信頼度付きで保存。時間経過で減衰し、低信頼度で削除。
```

LTMの内容は次回以降の会話でシステムプロンプトに自動挿入されます。  
各パラメータは `.env` の `STM_*` / `LTM_*` で調整可能です。

---

## 視覚認識機能（オプション）

`vision/vrc_person_speaker_listener.py` を有効にすると、  
VRChatの画面をキャプチャし、YOLOでプレイヤーを検出、OCRで名前を読み取り、  
誰が話しているかをDBに記録できます。

`.env` に以下を設定してください。

```env
YOLO_MODEL_PATH=./data/base.pt
PYTESSERACT_CMD=C:\Program Files\Tesseract-OCR\tesseract.exe
```

`app.py` 内の以下をアンコメントして有効化します。

```python
# from vision import vrc_person_speaker_listener
# vrc_person_speaker_listener.yolo_run()
```

---

## ウェイクワード

`.env` で設定したワードを含む発話のみAIが反応します。

```env
WAKE_WORD_ENABLED=True
WAKE_WORD=えーあい,AI,あい
```

会話中に以下のコマンドでオン/オフを切り替えられます。

- `呼びかけオン` → ウェイクワード有効化
- `呼びかけオフ` → 常時受付に切り替え

---

## カスタマイズ

- **LLMの変更**: `.env` の `LITELLM_MODEL` / `LITELLM_PROVIDER` を変更（LiteLLM対応プロバイダなら何でも使用可）
- **声の変更**: GPT-SoVITS 側のスピーカー設定と `GPT_SOVITS_REF_AUDIO` を変更
- **キャラクター変更**: `data/persona.txt` を編集
- **記憶の強さ調整**: `.env` の `STM_TO_LTM_WEIGHT`, `LTM_DECAY_RATE` 等を変更

---

## 今後の予定

- [ ] 👀 視覚認識の精度向上・VRChatOSC連携強化
- [ ] 🧍 自律移動AI
- [ ] 🎭 表情・ジェスチャー連動
- [ ] 🧠 長期記憶の最適化・要約機能

---

## 注意事項

- VRChatの[利用規約](https://hello.vrchat.com/legal)を遵守して使用してください
- 公開ワールド・他プレイヤーへのAI使用は配慮が必要です
- 本ツールは個人利用・研究目的を想定しています

---

## 動作確認環境

- MSI Stealth 14 AI Studio (Windows 11)
- RAM: 64GB (DDR5) / GPU: RTX 4070 Laptop / CPU: Intel Core Ultra 9 185H

---

## ライセンス

[MIT License](LICENSE)

## 作者

- GitHub: [@O-TYAN64](https://github.com/O-TYAN64)
