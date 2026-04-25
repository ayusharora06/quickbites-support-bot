-- Sample SQL queries to explore app.db
-- Run: sqlite3 data/app.db < data/sample_queries.sql

-- 1. A customer's recent orders (most recent first)
SELECT o.id, o.placed_at, o.status, o.total_inr, r.name AS restaurant
FROM orders o JOIN restaurants r ON r.id = o.restaurant_id
WHERE o.customer_id = 1
ORDER BY o.placed_at DESC
LIMIT 10;

-- 2. Customers with the highest complaint rate (per order)
SELECT c.id, c.name, c.loyalty_tier,
       COUNT(DISTINCT o.id) AS orders,
       COUNT(DISTINCT cp.id) AS complaints,
       ROUND(1.0 * COUNT(DISTINCT cp.id) / COUNT(DISTINCT o.id), 2) AS complaint_rate
FROM customers c
JOIN orders o ON o.customer_id = c.id
LEFT JOIN complaints cp ON cp.customer_id = c.id
GROUP BY c.id
HAVING orders >= 5
ORDER BY complaint_rate DESC
LIMIT 10;

-- 3. Restaurants ranked by average review rating
SELECT r.id, r.name, r.cuisine,
       ROUND(AVG(rv.rating), 2) AS avg_rating,
       COUNT(rv.id) AS n_reviews
FROM restaurants r
LEFT JOIN reviews rv ON rv.restaurant_id = r.id
GROUP BY r.id
ORDER BY avg_rating ASC NULLS LAST, n_reviews DESC;

-- 4. Riders with the most verified incidents
SELECT r.id, r.name, r.city,
       SUM(CASE WHEN i.verified = 1 THEN 1 ELSE 0 END) AS verified_incidents,
       SUM(CASE WHEN i.verified = 0 THEN 1 ELSE 0 END) AS unverified_incidents,
       COUNT(i.id) AS total_incidents
FROM riders r
LEFT JOIN rider_incidents i ON i.rider_id = r.id
GROUP BY r.id
ORDER BY verified_incidents DESC, total_incidents DESC
LIMIT 10;

-- 5. Total refunded per customer in the last 30 days
SELECT c.id, c.name, SUM(rf.amount_inr) AS refunded_inr, COUNT(rf.id) AS n_refunds
FROM customers c
JOIN refunds rf ON rf.customer_id = c.id
WHERE rf.issued_at >= date('2026-04-13', '-30 days')
GROUP BY c.id
ORDER BY refunded_inr DESC
LIMIT 10;

-- 6. Complaints that were rejected (likely spurious)
SELECT cp.id, c.name AS customer, cp.target_type, cp.description, cp.raised_at
FROM complaints cp
JOIN customers c ON c.id = cp.customer_id
WHERE cp.status = 'rejected'
ORDER BY cp.raised_at DESC
LIMIT 20;
