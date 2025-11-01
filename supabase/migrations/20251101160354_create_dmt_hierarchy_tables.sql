/*
  # Create DMT Classification Hierarchy Tables

  ## Description
  Creates the core DMT (Domain/Family/Class/Style) classification hierarchy tables
  to organize electronic components according to the universal DMT classification system.

  ## New Tables Created

  ### 1. `dmt_domains`
  Top-level classification (TT code: 00-99)
  - `id` - Auto-generated UUID primary key
  - `code` - Two-digit domain code (e.g., "01" for Passive Components)
  - `name` - Human-readable domain name
  - `description` - Optional detailed description
  - `created_at`, `updated_at` - Audit timestamps

  ### 2. `dmt_families`
  Second-level classification (FF code: 00-99 within domain)
  - `id` - Auto-generated UUID primary key
  - `domain_id` - Foreign key to dmt_domains
  - `code` - Two-digit family code (e.g., "01" for Capacitors)
  - `name` - Human-readable family name
  - `description` - Optional detailed description
  - `created_at`, `updated_at` - Audit timestamps

  ### 3. `dmt_classes`
  Third-level classification (CC code: 00-99, family-specific)
  - `id` - Auto-generated UUID primary key
  - `family_id` - Foreign key to dmt_families
  - `code` - Two-digit class code
  - `name` - Human-readable class name
  - `description` - Optional detailed description
  - `created_at`, `updated_at` - Audit timestamps

  ### 4. `dmt_styles`
  Fourth-level classification (SS code: 00-99, family-specific)
  - `id` - Auto-generated UUID primary key
  - `family_id` - Foreign key to dmt_families
  - `code` - Two-digit style code
  - `name` - Human-readable style name
  - `description` - Optional detailed description
  - `created_at`, `updated_at` - Audit timestamps

  ## Security
  - RLS (Row Level Security) is enabled on all tables
  - Public read access is granted for all classification tables
  - Only authenticated users can modify classification data

  ## Important Notes
  - All codes are stored as two-character strings (e.g., "01", "99")
  - The full DMT code format is: DMT-TTFFCCSSXXX
  - Cross-cutting class codes (90-99) have special meanings across all families
*/

-- Create dmt_domains table
CREATE TABLE IF NOT EXISTS dmt_domains (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  code text UNIQUE NOT NULL CHECK (length(code) = 2),
  name text NOT NULL,
  description text,
  created_at timestamptz DEFAULT now(),
  updated_at timestamptz DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_dmt_domains_code ON dmt_domains(code);

-- Create dmt_families table
CREATE TABLE IF NOT EXISTS dmt_families (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  domain_id uuid NOT NULL REFERENCES dmt_domains(id) ON DELETE CASCADE,
  code text NOT NULL CHECK (length(code) = 2),
  name text NOT NULL,
  description text,
  created_at timestamptz DEFAULT now(),
  updated_at timestamptz DEFAULT now(),
  UNIQUE(domain_id, code)
);

CREATE INDEX IF NOT EXISTS idx_dmt_families_domain_id ON dmt_families(domain_id);
CREATE INDEX IF NOT EXISTS idx_dmt_families_code ON dmt_families(code);

-- Create dmt_classes table
CREATE TABLE IF NOT EXISTS dmt_classes (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  family_id uuid NOT NULL REFERENCES dmt_families(id) ON DELETE CASCADE,
  code text NOT NULL CHECK (length(code) = 2),
  name text NOT NULL,
  description text,
  created_at timestamptz DEFAULT now(),
  updated_at timestamptz DEFAULT now(),
  UNIQUE(family_id, code)
);

CREATE INDEX IF NOT EXISTS idx_dmt_classes_family_id ON dmt_classes(family_id);
CREATE INDEX IF NOT EXISTS idx_dmt_classes_code ON dmt_classes(code);

-- Create dmt_styles table
CREATE TABLE IF NOT EXISTS dmt_styles (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  family_id uuid NOT NULL REFERENCES dmt_families(id) ON DELETE CASCADE,
  code text NOT NULL CHECK (length(code) = 2),
  name text NOT NULL,
  description text,
  created_at timestamptz DEFAULT now(),
  updated_at timestamptz DEFAULT now(),
  UNIQUE(family_id, code)
);

CREATE INDEX IF NOT EXISTS idx_dmt_styles_family_id ON dmt_styles(family_id);
CREATE INDEX IF NOT EXISTS idx_dmt_styles_code ON dmt_styles(code);

-- Enable Row Level Security
ALTER TABLE dmt_domains ENABLE ROW LEVEL SECURITY;
ALTER TABLE dmt_families ENABLE ROW LEVEL SECURITY;
ALTER TABLE dmt_classes ENABLE ROW LEVEL SECURITY;
ALTER TABLE dmt_styles ENABLE ROW LEVEL SECURITY;

-- Create RLS Policies for public read access

-- Domains policies
CREATE POLICY "Public can read domains"
  ON dmt_domains FOR SELECT
  TO public
  USING (true);

CREATE POLICY "Authenticated can insert domains"
  ON dmt_domains FOR INSERT
  TO authenticated
  WITH CHECK (true);

CREATE POLICY "Authenticated can update domains"
  ON dmt_domains FOR UPDATE
  TO authenticated
  USING (true)
  WITH CHECK (true);

CREATE POLICY "Authenticated can delete domains"
  ON dmt_domains FOR DELETE
  TO authenticated
  USING (true);

-- Families policies
CREATE POLICY "Public can read families"
  ON dmt_families FOR SELECT
  TO public
  USING (true);

CREATE POLICY "Authenticated can insert families"
  ON dmt_families FOR INSERT
  TO authenticated
  WITH CHECK (true);

CREATE POLICY "Authenticated can update families"
  ON dmt_families FOR UPDATE
  TO authenticated
  USING (true)
  WITH CHECK (true);

CREATE POLICY "Authenticated can delete families"
  ON dmt_families FOR DELETE
  TO authenticated
  USING (true);

-- Classes policies
CREATE POLICY "Public can read classes"
  ON dmt_classes FOR SELECT
  TO public
  USING (true);

CREATE POLICY "Authenticated can insert classes"
  ON dmt_classes FOR INSERT
  TO authenticated
  WITH CHECK (true);

CREATE POLICY "Authenticated can update classes"
  ON dmt_classes FOR UPDATE
  TO authenticated
  USING (true)
  WITH CHECK (true);

CREATE POLICY "Authenticated can delete classes"
  ON dmt_classes FOR DELETE
  TO authenticated
  USING (true);

-- Styles policies
CREATE POLICY "Public can read styles"
  ON dmt_styles FOR SELECT
  TO public
  USING (true);

CREATE POLICY "Authenticated can insert styles"
  ON dmt_styles FOR INSERT
  TO authenticated
  WITH CHECK (true);

CREATE POLICY "Authenticated can update styles"
  ON dmt_styles FOR UPDATE
  TO authenticated
  USING (true)
  WITH CHECK (true);

CREATE POLICY "Authenticated can delete styles"
  ON dmt_styles FOR DELETE
  TO authenticated
  USING (true);
