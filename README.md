# VRChat-AI

## 概要
VRChat上で動作するAIエージェントプロジェクトです。  
音声入力・AI応答・音声出力を組み合わせ、プレイヤーと自然な会話ができるシステムを目指しています。

---

## 特徴
- 🎤 音声認識（Speech-to-Text）
- 🧠 LLMによる会話生成
- 🔊 音声合成（GPT-SoVITS-v2pro）
- 🎮 VRChatとの連携（OSC）
- 💾 会話履歴・記憶機能（任意）

---

## 動作イメージ
1. ユーザーが話す  
2. 音声をテキスト化  
3. AIが応答生成  
4. 音声として返答  
5. VRChat上で会話成立  

---

## 技術スタック
- Python
- LiteLLM / OpenAI / Gemini など
- GPT-SoVITS-v2pro（TTS）
- Whisper系（STT）
- OSC通信（VRChat連携）
- SQLite（メモリ）

---

## セットアップ

### 1. リポジトリをクローン
```bash
git clone https://github.com/O-TYAN64/VRChat-AI.git
cd VRChat-AI
```

### 2. 仮想環境作成（推奨）
```bash
python -m venv venv
venv\Scripts\activate
```

### 3. 依存関係インストール
```bash
pip install -r requirements.txt
```

### 4. 環境変数設定
`.env` ファイルを作成：

```env
OPENAI_API_KEY=your_api_key
```

※使用するLLMに応じて変更してください

### 5. GPT-SoVITS起動
TTSエンジンを事前に起動してください（設定に応じて変更）

---

### 6. 実行
```bash
python main.py
```

---

## VRChat連携
- OSCを使用してアバターやチャットボックスと連携
- 表情・発話・動作などに応用可能

---


## カスタマイズ
- 使用するAIモデルの変更
- 声（GPT-SoVITS speaker）の変更
- キャラクター性のプロンプト設定
- 記憶機能の強化

---

## 今後の予定
- 👀 視覚認識（カメラ入力）
- 🧍 自律移動AI
- 🎭 表情・ジェスチャー連動
- 🧠 長期記憶の最適化

---

## 注意
- VRChatの利用規約を守って使用してください
- 公開環境でのAI使用には配慮が必要です

---

## ライセンス
MIT License

---

## 作者
- https://github.com/O-TYAN64