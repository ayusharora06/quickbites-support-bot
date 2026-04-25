# Data schema — `app.db`

This document describes every table in `app.db` in plain language, so that
non-engineers (e.g. Product Managers) can reason about the data without reading
SQL. All monetary values are in **INR** (Indian Rupees). All timestamps are
ISO‑8601 strings in UTC.

The database is a snapshot taken on **2026‑04‑13**. When you reason about
"recent" orders or "new" customers, use that as "today".

---

## `customers` — people who order food

| Column | Type | Meaning |
|---|---|---|
| `id` | integer | Unique customer id. |
| `name` | text | Full name. |
| `phone` | text | Phone number in E.164 format (`+91…`). |
| `email` | text | Email address. |
| `city` | text | City the customer usually orders in. |
| `joined_at` | text | When the account was created. Newer accounts with many complaints are a yellow flag. |
| `loyalty_tier` | text | `bronze` / `silver` / `gold`. Higher tiers have spent more historically. |
| `wallet_balance_inr` | integer | Pre-paid wallet credit currently held by the customer. |

## `restaurants` — places that prepare food

| Column | Type | Meaning |
|---|---|---|
| `id` | integer | Unique restaurant id. |
| `name` | text | Brand name. |
| `cuisine` | text | Primary cuisine category. |
| `city` | text | City the restaurant is in. |
| `area` | text | Locality / neighbourhood. |
| `joined_at` | text | When the restaurant was onboarded. |

## `riders` — delivery partners

| Column | Type | Meaning |
|---|---|---|
| `id` | integer | Unique rider id. |
| `name` | text | Full name. |
| `phone` | text | Phone number. |
| `city` | text | City they operate in. |
| `joined_at` | text | When the rider started on the platform. |

## `orders` — one row per order placed

| Column | Type | Meaning |
|---|---|---|
| `id` | integer | Unique order id. |
| `customer_id` | integer | → `customers.id` |
| `restaurant_id` | integer | → `restaurants.id` |
| `rider_id` | integer or null | → `riders.id`. `NULL` for cancelled orders. |
| `placed_at` | text | When the customer placed the order. |
| `delivered_at` | text or null | When the rider marked it delivered. `NULL` if cancelled. |
| `status` | text | `delivered` or `cancelled`. |
| `subtotal_inr` | integer | Sum of item prices × quantities. |
| `delivery_fee_inr` | integer | Delivery fee. |
| `total_inr` | integer | `subtotal_inr + delivery_fee_inr`. |
| `payment_method` | text | `upi` / `card` / `wallet` / `cod`. |
| `promo_code` | text or null | Promo code applied, if any. |
| `address` | text | Delivery address. |

## `order_items` — the individual items in each order

| Column | Type | Meaning |
|---|---|---|
| `id` | integer | Unique item line id. |
| `order_id` | integer | → `orders.id` |
| `item_name` | text | Name of the dish. |
| `qty` | integer | Quantity ordered. |
| `price_inr` | integer | Per-unit price. |

## `complaints` — issues raised by customers

| Column | Type | Meaning |
|---|---|---|
| `id` | integer | Unique complaint id. |
| `customer_id` | integer | Who raised it. |
| `order_id` | integer | Which order it is about. |
| `target_type` | text | `restaurant` / `rider` / `app` — who or what the complaint is against. |
| `target_id` | integer or null | The restaurant or rider id, if applicable. |
| `raised_at` | text | When the complaint was filed. |
| `description` | text | Free-text description from the customer. |
| `status` | text | `open` / `resolved` / `rejected`. |
| `resolution` | text | `refund_full` / `refund_partial` / `credit` / `apology` / `none`. |
| `resolution_amount_inr` | integer | Money or credit granted. 0 if none. |

## `refunds` — money or credit returned to customers

| Column | Type | Meaning |
|---|---|---|
| `id` | integer | Unique refund id. |
| `customer_id` | integer | Who received the refund. |
| `order_id` | integer | Which order. |
| `amount_inr` | integer | Amount refunded. |
| `type` | text | `cash` (back to original payment method) or `wallet_credit`. |
| `issued_at` | text | When the refund was issued. |
| `reason` | text | Short reason attached to the refund. |

## `reviews` — ratings customers leave for restaurants

| Column | Type | Meaning |
|---|---|---|
| `id` | integer | Unique review id. |
| `customer_id` | integer | Reviewer. |
| `order_id` | integer | Order the review is for. |
| `restaurant_id` | integer | Restaurant being reviewed. |
| `rating` | integer | 1–5 stars. |
| `comment` | text | Free-text comment. May be empty. |
| `created_at` | text | When the review was left. |

## `rider_incidents` — things that went wrong on a specific delivery

| Column | Type | Meaning |
|---|---|---|
| `id` | integer | Unique incident id. |
| `rider_id` | integer | Rider involved. |
| `order_id` | integer | Order it happened on. |
| `type` | text | `late` / `rude` / `damaged` / `theft_claim`. |
| `reported_at` | text | When it was reported. |
| `verified` | integer | `1` if operations verified the incident, `0` if not. |
| `notes` | text | Free-text notes. |

---

## Hints for reasoning about the data

- A customer whose **complaint rate is much higher than average** and whose
  complaints are often **rejected** or result in **zero payout** is a likely
  abuser.
- A customer who has **received many full refunds on high-value orders in a
  short window** is a yellow flag, even if each complaint looks legitimate in
  isolation.
- A rider with many **verified** incidents (especially `theft_claim` or
  `rude`) is a real problem; one with many **unverified** `theft_claim`
  reports from the same handful of customers is more likely a victim of
  spurious claims.
- Low-rated restaurants tend to have lots of 1–2 star reviews and a higher
  rate of `cold food` / `missing item` complaints.
- `joined_at` matters: a brand-new account that is already filing multiple
  complaints is a stronger abuse signal than an old account doing the same.
