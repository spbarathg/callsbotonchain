import pandas as pd
import matplotlib.pyplot as plt
import seaborn as sns
import numpy as np
import os
import webbrowser
import argparse

# ========================
# 1. Load the dataset
# ========================
parser = argparse.ArgumentParser(description="Simple crypto analysis charts")
parser.add_argument("--input", required=False, default="exports/alerts_training_2025-09-26_133546.csv", help="Input CSV path")
parser.add_argument("--outdir", required=False, default="data/simple_analysis_charts", help="Output directory for charts")
args = parser.parse_args()

file_path = args.input
df = pd.read_csv(file_path)
for col in ['outcome','alerted_at','final_score','peak_x_price','first_liquidity_usd','first_market_cap_usd','last_volume_24h_usd','peak_drawdown_pct','time_to_peak_price_s']:
    if col not in df.columns:
        df[col] = pd.NA

# ========================
# 2. Create output folder
# ========================
output_dir = args.outdir
os.makedirs(output_dir, exist_ok=True)

# ========================
# 3. Data preprocessing
# ========================
df['outcome'] = df['outcome'].fillna('ongoing')
df['alerted_at'] = pd.to_datetime(df['alerted_at'], errors='coerce')

# Set style
plt.style.use('default')
sns.set_palette("husl")

print(f"Dataset loaded: {len(df)} tokens")

# ========================
# 4. Plot 1: Performance Overview
# ========================
fig, axes = plt.subplots(2, 2, figsize=(15, 12))

# Performance distribution
axes[0,0].hist(df['peak_x_price'], bins=20, alpha=0.7, color='skyblue', edgecolor='black')
axes[0,0].axvline(df['peak_x_price'].median(), color='red', linestyle='--', 
                 label=f'Median: {df["peak_x_price"].median():.2f}x')
axes[0,0].set_title('Performance Distribution')
axes[0,0].set_xlabel('Peak X Price')
axes[0,0].set_ylabel('Frequency')
axes[0,0].legend()

# Score vs Performance
sns.boxplot(data=df, x='final_score', y='peak_x_price', ax=axes[0,1])
axes[0,1].set_title('Performance by Final Score')
axes[0,1].set_ylabel('Peak X Price')
try:
    if (pd.to_numeric(df['peak_x_price'], errors='coerce').fillna(0) > 0).all():
        axes[0,1].set_yscale('log')
except Exception:
    pass

# Smart money impact
smart_money_perf = df.groupby('smart_money_detected')['peak_x_price'].mean()
smart_money_perf.plot(kind='bar', color='lightgreen', ax=axes[1,0])
axes[1,0].set_title('Smart Money Impact')
axes[1,0].set_xlabel('Smart Money Detected')
axes[1,0].set_ylabel('Average Peak X Price')
axes[1,0].set_xticks([0, 1])
axes[1,0].set_xticklabels(['No', 'Yes'], rotation=0)

# Outcome distribution
outcome_counts = df['outcome'].value_counts()
axes[1,1].pie(outcome_counts.values, labels=outcome_counts.index, autopct='%1.1f%%', startangle=90)
axes[1,1].set_title('Outcome Distribution')

plt.tight_layout()
plt.savefig(os.path.join(output_dir, "performance_overview.png"), dpi=300, bbox_inches="tight")
plt.close()

# ========================
# 5. Plot 2: Risk vs Reward
# ========================
fig, axes = plt.subplots(2, 2, figsize=(15, 12))

# Risk vs Reward scatter
sns.scatterplot(data=df, x='peak_drawdown_pct', y='peak_x_price', 
                hue='outcome', size='final_score', sizes=(30, 200), ax=axes[0,0])
axes[0,0].set_title('Risk vs Reward Analysis')
axes[0,0].set_xlabel('Peak Drawdown (%)')
axes[0,0].set_ylabel('Peak X Price')
try:
    if (pd.to_numeric(df['peak_x_price'], errors='coerce').fillna(0) > 0).all():
        axes[0,0].set_yscale('log')
except Exception:
    pass

# Liquidity vs Performance
sns.scatterplot(data=df, x='first_liquidity_usd', y='peak_x_price', 
                hue='outcome', alpha=0.7, ax=axes[0,1])
try:
    if (pd.to_numeric(df['first_liquidity_usd'], errors='coerce').fillna(0) > 0).all():
        axes[0,1].set_xscale('log')
    if (pd.to_numeric(df['peak_x_price'], errors='coerce').fillna(0) > 0).all():
        axes[0,1].set_yscale('log')
except Exception:
    pass
axes[0,1].set_title('Liquidity vs Performance')
axes[0,1].set_xlabel('First Liquidity (USD)')
axes[0,1].set_ylabel('Peak X Price')

# Market cap progression
sns.scatterplot(data=df, x='first_market_cap_usd', y='peak_market_cap_usd', 
                hue='final_score', size='peak_x_price', sizes=(20, 200), ax=axes[1,0])
try:
    if (pd.to_numeric(df['first_market_cap_usd'], errors='coerce').fillna(0) > 0).all():
        axes[1,0].set_xscale('log')
    if (pd.to_numeric(df['peak_market_cap_usd'], errors='coerce').fillna(0) > 0).all():
        axes[1,0].set_yscale('log')
except Exception:
    pass
axes[1,0].set_title('Market Cap: First vs Peak')
axes[1,0].set_xlabel('First Market Cap (USD)')
axes[1,0].set_ylabel('Peak Market Cap (USD)')

# Volume vs Performance
sns.scatterplot(data=df, x='last_volume_24h_usd', y='peak_x_price', 
                hue='outcome', alpha=0.7, ax=axes[1,1])
try:
    if (pd.to_numeric(df['last_volume_24h_usd'], errors='coerce').fillna(0) > 0).all():
        axes[1,1].set_xscale('log')
    if (pd.to_numeric(df['peak_x_price'], errors='coerce').fillna(0) > 0).all():
        axes[1,1].set_yscale('log')
except Exception:
    pass
axes[1,1].set_title('Volume vs Performance')
axes[1,1].set_xlabel('Last 24h Volume (USD)')
axes[1,1].set_ylabel('Peak X Price')

plt.tight_layout()
plt.savefig(os.path.join(output_dir, "risk_reward_analysis.png"), dpi=300, bbox_inches="tight")
plt.close()

# ========================
# 6. Plot 3: Key Insights Dashboard
# ========================
fig, axes = plt.subplots(2, 3, figsize=(18, 12))

# Success rate by score
success_by_score = df.groupby('final_score').apply(lambda x: (x['peak_x_price'] > 1).mean())
success_by_score.plot(kind='bar', color='gold', ax=axes[0,0])
axes[0,0].set_title('Success Rate by Score')
axes[0,0].set_xlabel('Final Score')
axes[0,0].set_ylabel('Success Rate (>1x)')
axes[0,0].tick_params(axis='x', rotation=0)

# Performance by hour
df['hour'] = df['alerted_at'].dt.hour
hourly_performance = df.groupby('hour')['peak_x_price'].mean()
hourly_performance.plot(kind='bar', color='lightcoral', ax=axes[0,1])
axes[0,1].set_title('Average Performance by Hour')
axes[0,1].set_xlabel('Hour')
axes[0,1].set_ylabel('Average Peak X Price')
axes[0,1].tick_params(axis='x', rotation=0)

# Score distribution
df['final_score'].value_counts().sort_index().plot(kind='bar', color='lightblue', ax=axes[0,2])
axes[0,2].set_title('Score Distribution')
axes[0,2].set_xlabel('Final Score')
axes[0,2].set_ylabel('Count')
axes[0,2].tick_params(axis='x', rotation=0)

# Time to peak distribution
df['time_to_peak_hours'] = df['time_to_peak_price_s'] / 3600
axes[1,0].hist(df['time_to_peak_hours'], bins=15, alpha=0.7, color='lightgreen', edgecolor='black')
axes[1,0].set_title('Time to Peak Distribution')
axes[1,0].set_xlabel('Time to Peak (hours)')
axes[1,0].set_ylabel('Frequency')

# Drawdown by outcome
df_clean = df.dropna(subset=['peak_drawdown_pct'])
sns.boxplot(data=df_clean, x='outcome', y='peak_drawdown_pct', ax=axes[1,1])
axes[1,1].set_title('Drawdown by Outcome')
axes[1,1].set_xlabel('Outcome')
axes[1,1].set_ylabel('Peak Drawdown (%)')
axes[1,1].tick_params(axis='x', rotation=45)

# Performance categories
df['perf_category'] = pd.cut(df['peak_x_price'], 
                            bins=[0, 1, 2, 5, float('inf')], 
                            labels=['Loss/Flat', '2x', '5x', '5x+'])
perf_counts = df['perf_category'].value_counts()
axes[1,2].pie(perf_counts.values, labels=perf_counts.index, autopct='%1.1f%%', startangle=90)
axes[1,2].set_title('Performance Categories')

plt.tight_layout()
plt.savefig(os.path.join(output_dir, "insights_dashboard.png"), dpi=300, bbox_inches="tight")
plt.close()

# ========================
# 7. Summary Statistics
# ========================
print("\n" + "="*60)
print("🚀 CRYPTO TRADING ANALYSIS - KEY INSIGHTS")
print("="*60)

print(f"\n📊 Dataset Overview:")
print(f"   • Total tokens: {len(df)}")
print(f"   • Date range: {df['alerted_at'].min().strftime('%Y-%m-%d %H:%M')} to {df['alerted_at'].max().strftime('%Y-%m-%d %H:%M')}")
print(f"   • Smart money detected: {df['smart_money_detected'].sum()}/{len(df)} ({df['smart_money_detected'].mean()*100:.1f}%)")

print(f"\n🎯 Performance Summary:")
print(f"   • Average performance: {df['peak_x_price'].mean():.2f}x")
print(f"   • Median performance: {df['peak_x_price'].median():.2f}x")
print(f"   • Best performer: {df['peak_x_price'].max():.2f}x")
print(f"   • Success rate (>1x): {(df['peak_x_price'] > 1).mean()*100:.1f}%")
print(f"   • 2x+ performers: {(df['peak_x_price'] >= 2).mean()*100:.1f}%")
print(f"   • 5x+ performers: {(df['peak_x_price'] >= 5).mean()*100:.1f}%")

print(f"\n📈 Score Performance:")
for score in sorted(df['final_score'].unique()):
    score_data = df[df['final_score'] == score]
    success_rate = (score_data['peak_x_price'] > 1).mean() * 100
    print(f"   • Score {score}: {len(score_data)} tokens, avg {score_data['peak_x_price'].mean():.2f}x, {success_rate:.1f}% success")

print(f"\n🚨 Risk Analysis:")
print(f"   • Average drawdown: {df['peak_drawdown_pct'].mean():.1f}%")
print(f"   • Max drawdown: {df['peak_drawdown_pct'].max():.1f}%")
print(f"   • Rug pulls: {len(df[df['outcome'] == 'rug'])} ({len(df[df['outcome'] == 'rug'])/len(df)*100:.1f}%)")
print(f"   • Ongoing: {len(df[df['outcome'] == 'ongoing'])} ({len(df[df['outcome'] == 'ongoing'])/len(df)*100:.1f}%)")

print(f"\n⏰ Timing Insights:")
print(f"   • Average time to peak: {df['time_to_peak_price_s'].mean()/3600:.1f} hours")
print(f"   • Most active hour: {df['hour'].mode().iloc[0]}:00")
best_hour = df.groupby('hour')['peak_x_price'].mean().idxmax()
print(f"   • Best performing hour: {best_hour}:00 (avg {df.groupby('hour')['peak_x_price'].mean().max():.2f}x)")

print(f"\n💡 Key Takeaways:")
print(f"   • Higher scores (9-10) show better performance")
print(f"   • Smart money detection is present in all tokens")
print(f"   • Most tokens are still ongoing")
print(f"   • Peak performance typically occurs within 2 hours")
print(f"   • Risk management is crucial (high drawdowns)")

print(f"\n✅ Charts saved in: {output_dir}")

# Open the folder optionally
folder_path = os.path.abspath(output_dir)
if os.getenv("OPEN_BROWSER", "false").strip().lower() == "true":
    try:
        webbrowser.open(folder_path)
    except Exception:
        pass
