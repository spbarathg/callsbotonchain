# Leaderboard

Keep track of all your calls in your Group using the **Phanes Leaderboard**.

## 👨‍💻 How It Works

**Every new** [queried coin ](https://docs.phanes.bot/commands#price-queries)will be added to the tracking system automatically.

If you are only scanning a coin **you'd have to click** on the <img src="https://4017490896-files.gitbook.io/~/files/v0/b/gitbook-x-prod.appspot.com/o/spaces%2FnQJ6MRzOU9wi6ToZ6gX5%2Fuploads%2Fo9KTUIOsAkF2rZ3iZOxR%2Fscan%20button.png?alt=media&#x26;token=4437576b-a76a-4122-8468-4c11458fcb24" alt="" data-size="line"> button.

The button expires after **2 minutes**. After the time has elapsed, the option to remove the call is no longer available.

{% tabs %}
{% tab title="⭐️ Example" %}

<figure><img src="https://4017490896-files.gitbook.io/~/files/v0/b/gitbook-x-prod.appspot.com/o/spaces%2FnQJ6MRzOU9wi6ToZ6gX5%2Fuploads%2FK8fob7wGMFLPQq4RM10S%2Flb.png?alt=media&#x26;token=6820267e-9fc8-4f5a-a779-4ad0d03aa5b4" alt="" width="375"><figcaption></figcaption></figure>

{% hint style="info" %}
Top Callers are determined by a **points-based system**. To be eligible for the list, you must have earned at least 1 point. Learn more [here](#points-system).
{% endhint %}
{% endtab %}

{% tab title="🐲 Emoji Guide" %}
The first emoji represents the user's rank, more [here](https://docs.phanes.bot/phanes/leaderboard#emoji-ranks).&#x20;

The second emoji represents the chain:

| Emoji         | Definition                              |
| ------------- | --------------------------------------- |
| 💊            | Called on Pump.Fun **before migration** |
| 🟣            | Solana                                  |
| 🔷            | Ethereum                                |
| 🔵            | Base                                    |
| 🔸            | BSC                                     |
| 🟡            | Ton                                     |
| 🔺            | Avax                                    |
| ♦️            | Tron                                    |
| {% endtab %}  |                                         |
| {% endtabs %} |                                         |

{% hint style="warning" %}

### We Recommend

1. Turn off [**anonymous appearance**](#user-content-fn-1)[^1] in your group.
2. Set a [**Telegram Username**](https://telegram.org/blog/usernames-and-secret-chats-v2?setln=it) to avoid appearing as "Anonymous" or "None" on the Leaderboard.
   {% endhint %}

***

## 🎮 Commands

* `/lb` or `/leaderboard`
  * For periods > 1 day, only these are allowed:\
    `1d, 2d, 3d, 4d, 5d, 6d, 7d, 14d, 1mo, 2mo, 3mo, 4mo, 5mo`.
  * View a longer leaderboard with: `/lb 1d 25` which returns the top 25.
  * Set a minimum ATH: `/lb 1d $1m`, `/lb $500k`.
  * Hide names: `/lb anon`, `/lb 7d anon`.
* `/wlb`: View the Web Leaderboard
* `/calls`: [View the last 10 calls.](#user-content-fn-2)[^2]
* `/stats <@username>`: View user's stats from your group. For more click [here](#user-stats).
* `/pnl <coin/ca>` & `/gpnl <period>`: Generate a PNL / Group PNL image.
* `/fc <coin/ca>`: [Get first caller information](#user-content-fn-3)[^3].
* `/elb`: Export the leaderboard into a CSV file. For more click [here](https://docs.phanes.bot/phanes/leaderboard#export-leaderboard).

***

## ⚡️ Core Performance Metrics

### **Top Callers** <a href="#mvp" id="mvp"></a>

The Top Callers system is based on the user rankings point system. It highlights the most successful callers based on their accumulated points from all calls within the specified timeframe. Points are awarded according to the [points system](#points-system).

### Hit Rate

The hit rate shows how consistently a caller finds tokens that achieve significant gains. It's calculated as the percentage of calls that reach at least 2x return. For example, a 40% hit rate means that 4 out of 10 calls reached or exceeded 2x return. This metric helps identify callers who consistently spot potential winners rather than those who might get lucky with one big call.

### **Average Return**

The average return (mean) represents the typical performance across all calls. It's calculated by adding up all returns and dividing by the number of calls. While this gives a good overall performance indicator, it can be heavily influenced by extremely successful calls. For instance, one 100x call among many smaller returns will significantly boost the average, which might not represent the typical performance.

### **Median Return**

The median return provides the middle value when all returns are ordered from lowest to highest. Unlike the average, it's not skewed by extremely high or low returns, making it often a better representation of typical performance. If a caller has a median return of 3x, it means half their calls performed better than 3x and half performed worse. This metric is particularly useful for understanding a caller's consistent performance level.

> *To learn more about median* [*click here*](https://www.investopedia.com/terms/m/median.asp)*.*

{% hint style="success" %}
Together, these metrics provide a comprehensive view:

* **Top Callers** shows relative performance ranking based on the point system.
* **Hit Rate** shows consistency in finding winners.
* **Average Return** shows overall performance including big wins.
* **Median Return** shows typical performance excluding outliers.

Using all these metrics gives the most accurate picture of a caller's performance, as each metric compensates for the limitations of the others.
{% endhint %}

***

## 🖥️ Ranking System

The user rankings are calculated using a point-based system that rewards or penalizes users based on the performance of their calls. Here's how points are assigned:

### **How It Works**

* Each user starts with 0 points
* Points are accumulated for each call based on its performance
* Poor calls result in negative points to penalize bad performance
* Higher multipliers earn exponentially more points to reward exceptional calls
* Final rankings are sorted from highest to lowest total points

### **Scoring Tiers**

{% tabs %}
{% tab title="🧮 Points System" %}

### **How points are awarded per call**

#### Base Points

* **-2** points » below 1x
* **-1** point » 1x to 1.3x
* **0** points » 1.3x to 1.8x
* **+1** point » 1.8x to 5x
* **+2** points » 5x to 10x
* **+3** points » 10x to 20x
* **+4** points » 20x to 50x
* **+7** points » 50x to 100x
* **+10** points » 100x to 200x
* **+15** points » 200x or higher

#### **Market Cap Multiplier**

* Below $25k MC: ×0.5 (half points)
* $25k - $50k MC: ×0.75 (25% reduced points)
* $50k - $1M MC: ×1.0 (normal points)
* Above $1M MC: ×1.5 (50% bonus points)

*(only applies to positive number)*
{% endtab %}

{% tab title="☎️ Caller Ranking" %}
**Emoji shown next to user's total points.**

* 😭 Negative points
* 😊 0 to 1 points
* 😎 2 to 4 points
* 🎉 5 to 9 points
* 💸 10 to 14 points
* 🔥 15 to 19 points
* 🚀 20 to 29 points
* 🌙 30+ points
  {% endtab %}

{% tab title="⚡️ Return Multiplier" %}
**Emoji shown next to individual calls.**

* 😭 Below 1.2x
* 🥱 1.2x to 1.8x
* 😎 1.8x to 5x
* 🎉 5x to 15x
* 💸 15x to 30x
* 🔥 30x to 50x
* 🚀 50x to 100x
* 🌙 100x or higher
  {% endtab %}
  {% endtabs %}

{% hint style="success" %}
This System:

* Rewards consistency and high-performance calls.
* Penalizes poor calls and pump chasing.
* Provides more weight to exceptional performances.
* Creates a balanced scoring system that reflects both consistency and ability to spot big winners.

The final user rankings provide a competitive leaderboard that reflects both the quality and consistency of a user's calling ability.
{% endhint %}

***

## 👨‍🍳 User Stats

You are able to view user stats by either clicking on the user's name within the leaderboard or by using the command: `/stats <@username>`.

{% hint style="warning" %}
Phanes always verifies that the user requesting statistics is a member of the group, to prevent unauthorized access. **To ensure this security measure works effectively, Phanes requires admin privileges in your group.**
{% endhint %}

<figure><img src="https://4017490896-files.gitbook.io/~/files/v0/b/gitbook-x-prod.appspot.com/o/spaces%2FnQJ6MRzOU9wi6ToZ6gX5%2Fuploads%2F7uyN0Y8QIJ12G7ivV6En%2Fstats.png?alt=media&#x26;token=222f5421-62c0-45da-a3b8-78274ec66ab2" alt="" width="320"><figcaption></figcaption></figure>

***

## 📸 PNL Card

We offer **free custom-designed** PNL cards for every first caller in your group.

The X return is specifically calculated using:

* The market cap at the time of first call in the group
* The highest market cap reached after the call (ATH)

You can generate a PNL image with `/pnl <symbol/ca>` or by clicking on an emoji within your `/leaderboard`.

<figure><img src="https://4017490896-files.gitbook.io/~/files/v0/b/gitbook-x-prod.appspot.com/o/spaces%2FnQJ6MRzOU9wi6ToZ6gX5%2Fuploads%2FtnscssZCOdKfD6ZwaREC%2F70870.png?alt=media&#x26;token=4e467770-0c95-4521-ad03-eee2b1abdcce" alt=""><figcaption></figcaption></figure>

***

## 📸 Group PNL Card

You can generate a Group PNL with `/gpnl <period>`, e.g. `/gpnl 7d`.

<figure><img src="https://4017490896-files.gitbook.io/~/files/v0/b/gitbook-x-prod.appspot.com/o/spaces%2FnQJ6MRzOU9wi6ToZ6gX5%2Fuploads%2F4snejE63fdk9BmNNO0sZ%2Ftest_group_pnl.jpg?alt=media&#x26;token=7047c496-94d9-4e67-ac7a-7e0fffb84184" alt=""><figcaption><p>Group PNL Image</p></figcaption></figure>

***

## 📂 Export Leaderboard

[phanes-pro](https://docs.phanes.bot/premium/phanes-pro "mention") subscribers are able to export the Leaderboard to a CSV file with `/elb <period>`.

{% hint style="info" %}
Group admins can limit the use of this command to admins only by using `/allow_elb <on/off>`.
{% endhint %}

<figure><img src="https://4017490896-files.gitbook.io/~/files/v0/b/gitbook-x-prod.appspot.com/o/spaces%2FnQJ6MRzOU9wi6ToZ6gX5%2Fuploads%2FzREVECvayIlH6Xs7AunR%2F92920.png?alt=media&#x26;token=f996d965-cf17-4f05-ab9f-5bbf16184257" alt=""><figcaption></figcaption></figure>

[^1]: To turn off the anonymous mode go into your group settings » Administrators » Right click the user you want to edit » Edit admin rights » Toggle off "Remain anonymous".

[^2]: ![](https://4017490896-files.gitbook.io/~/files/v0/b/gitbook-x-prod.appspot.com/o/spaces%2FnQJ6MRzOU9wi6ToZ6gX5%2Fuploads%2FTsq3Hun5g2ziPFV7Eofv%2Flc.png?alt=media\&token=5b46b052-1133-473b-a602-41fc503dbd81)

[^3]: ![](https://4017490896-files.gitbook.io/~/files/v0/b/gitbook-x-prod.appspot.com/o/spaces%2FnQJ6MRzOU9wi6ToZ6gX5%2Fuploads%2FNDcHyI8GtdaCmlhidOTi%2F36697.png?alt=media\&token=6fa54767-bd9f-4216-854a-86179faf3f4e)