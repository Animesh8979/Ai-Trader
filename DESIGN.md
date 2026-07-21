---
name: Godmode Bloomberg Terminal
version: 3.5.0
author: Antigravity AI Staff Software Architect

colors:
  primary: "#00F0FF"        # Cyber Neon Cyan
  accent: "#7B2CBF"         # Deep Quantum Purple
  success: "#00F5D4"        # Ultra Mint / Bull Green
  danger: "#FF0055"         # High-Frequency Crimson / Bear Red
  warning: "#FFBE0B"        # Amber Warning / Risk Yellow
  info: "#3A86FF"           # Telemetry Blue
  background: "#030712"     # Deep Void Obsidian
  surface: "rgba(10, 15, 30, 0.75)"  # Glassmorphism Panel Surface
  surfaceBorder: "rgba(0, 240, 255, 0.15)" # Subtle Cyan Border
  textPrimary: "#F8FAFC"    # Crisp Slate White
  textSecondary: "#94A3B8"  # Subdued Steel Gray
  goldBloomberg: "#FFAA00"  # Classic Bloomberg Amber Ticker

typography:
  fontFamilyMono: "'JetBrains Mono', 'Fira Code', 'Courier New', monospace"
  fontFamilySans: "'Inter', 'Outfit', system-ui, -apple-system, sans-serif"
  h1: { fontFamily: "fontFamilyMono", fontSize: "1.75rem", fontWeight: 800, letterSpacing: "0.1em" }
  h2: { fontFamily: "fontFamilyMono", fontSize: "1.25rem", fontWeight: 700, letterSpacing: "0.08em" }
  h3: { fontFamily: "fontFamilySans", fontSize: "1.00rem", fontWeight: 600 }
  body-md: { fontFamily: "fontFamilySans", fontSize: "0.875rem", lineHeight: "1.5" }
  mono-ticker: { fontFamily: "fontFamilyMono", fontSize: "0.825rem", fontWeight: 700 }

rounded:
  sm: "4px"
  md: "8px"
  lg: "12px"
  pill: "9999px"

spacing:
  xs: "4px"
  sm: "8px"
  md: "16px"
  lg: "24px"
  xl: "32px"

shadows:
  glass: "0 8px 32px 0 rgba(0, 0, 0, 0.37)"
  neonCyan: "0 0 20px rgba(0, 240, 255, 0.35)"
  neonGreen: "0 0 20px rgba(0, 245, 212, 0.35)"
  neonRed: "0 0 20px rgba(255, 0, 85, 0.35)"

layout:
  gridColumns: 12
  headerHeight: "64px"
  tickerHeight: "36px"
  dualMonitorSplit: "50% / 50%"
---

# Godmode Terminal — Visual Identity & Design System

## Overview
Godmode Terminal is a SOTA, zero-compromise quantitative trading interface combining Bloomberg Terminal functional density with modern dark glassmorphic cyber-aesthetics. It empowers zero-knowledge and institutional traders alike with real-time telemetry, live news tickers faster than TV, Level 2 orderbook depth, interactive RL agent state visualizers, and multi-exchange execution.

## Core Design Principles

### 1. High Contrast & High Information Density
- Dark Obsidian background (`#030712`) paired with high-contrast text (`#F8FAFC`).
- Financial metrics utilize strict color coding: Mint (`#00F5D4`) for gains/bullish, Crimson (`#FF0055`) for drawdowns/bearish, Amber (`#FFAA00`) for tickers/warnings.
- Data tables use fixed-width monospace typography (`JetBrains Mono`) for instantaneous legibility.

### 2. Multi-Screen Dual Terminal Architecture
- **Screen 1 (Indian Equities & Domestic Wire)**: Live NSE/BSE tickers, Nifty 50 / BankNifty orderbook, Moneycontrol & ET sub-second news wire before TV, Shoonya zero-brokerage execution HUD.
- **Screen 2 (International & Crypto Terminal)**: BTC/ETH Level 2 DOM canvas, global macro wire, Binance WebSocket feed, RL TensorTrade agent training monitor.

### 3. Glassmorphism & Cyber Motion
- Panel cards utilize backdrop blur filters (`backdrop-filter: blur(12px)`) over translucent dark glass (`rgba(10, 15, 30, 0.75)`).
- Micro-animations via GSAP and HTML5 Canvas for real-time particle background grids, DOM depth ladders, and neural debate DAG node pulses.

### 4. Zero-Intervention Autopilot HUD
- Prominent status indicator badges: `RUNNING` (Green glow), `HALTED` (Red glow), `RECOVERING` (Amber pulse).
- Emergency Halt / Engage buttons with magnetic cursor hover effects and confirmation dialogs.
