# Changelog

All notable changes to tillroll are recorded here.

## [Unreleased]

## [1.4.2] - 2026-09-17

### Fixed

- `Order.total_display` pads pence to two digits (OPS-180).

## [1.4.1] - 2026-08-27

### Fixed

- Order totals no longer drop the final line when it is zero (OPS-171).

## [1.4.0] - 2026-08-06

### Added

- Products table with prices in minor units (OPS-188).
- Index on orders by customer (OPS-140).

### Changed

- Order status defaults to `pending` (OPS-117).

[Unreleased]: https://git.tillroll.example/tillroll/compare/v1.4.2...HEAD
[1.4.2]: https://git.tillroll.example/tillroll/compare/v1.4.1...v1.4.2
[1.4.1]: https://git.tillroll.example/tillroll/compare/v1.4.0...v1.4.1
[1.4.0]: https://git.tillroll.example/tillroll/compare/v1.3.0...v1.4.0
