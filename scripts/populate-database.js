#!/usr/bin/env node

const fs = require('fs');
const path = require('path');
const { createClient } = require('@supabase/supabase-js');
const csv = require('csv-parser');

// Load environment variables
require('dotenv').config({ path: path.join(__dirname, '..', '.env') });

const supabaseUrl = process.env.VITE_SUPABASE_URL;
const supabaseKey = process.env.VITE_SUPABASE_SUPABASE_ANON_KEY;

if (!supabaseUrl || !supabaseKey) {
  console.error('Missing Supabase credentials in .env file');
  process.exit(1);
}

const supabase = createClient(supabaseUrl, supabaseKey);

// Paths
const schemaPath = path.join(__dirname, '..', 'partsdb', '_csv_renderer', 'dmt_schema.json');
const templatesPath = path.join(__dirname, '..', 'partsdb', '_csv_renderer', 'dmt_templates.json');
const csvPath = path.join(__dirname, '..', 'partsdb', '_csv_renderer', 'DMT_Partslib.csv');

async function populateDMTHierarchy() {
  console.log('Reading DMT schema...');
  const schema = JSON.parse(fs.readFileSync(schemaPath, 'utf-8'));

  console.log('Populating DMT hierarchy...');

  // Populate domains
  for (const domain of schema.domains) {
    console.log(`  Processing domain ${domain.tt}: ${domain.name}`);

    const { data: existingDomain } = await supabase
      .from('dmt_domains')
      .select('id')
      .eq('code', domain.tt)
      .maybeSingle();

    let domainId;
    if (existingDomain) {
      domainId = existingDomain.id;
    } else {
      const { data: insertedDomain, error } = await supabase
        .from('dmt_domains')
        .insert({ code: domain.tt, name: domain.name })
        .select()
        .single();

      if (error) {
        console.error(`    Error inserting domain: ${error.message}`);
        continue;
      }
      domainId = insertedDomain.id;
    }

    // Populate families
    if (domain.families) {
      for (const family of domain.families) {
        console.log(`    Processing family ${family.ff}: ${family.name}`);

        const { data: existingFamily } = await supabase
          .from('dmt_families')
          .select('id')
          .eq('domain_id', domainId)
          .eq('code', family.ff)
          .maybeSingle();

        if (!existingFamily) {
          const { error } = await supabase
            .from('dmt_families')
            .insert({
              domain_id: domainId,
              code: family.ff,
              name: family.name
            });

          if (error) {
            console.error(`      Error inserting family: ${error.message}`);
          }
        }
      }
    }
  }

  console.log('DMT hierarchy populated successfully!');
}

async function importCSVData() {
  console.log('\nImporting CSV data...');

  const templates = JSON.parse(fs.readFileSync(templatesPath, 'utf-8'));
  const components = [];

  return new Promise((resolve, reject) => {
    fs.createReadStream(csvPath)
      .pipe(csv())
      .on('data', (row) => {
        // Extract DMT codes
        const mpn = row.MPN;
        const tt = row.TT;
        const ff = row.FF;
        const cc = row.CC;
        const ss = row.SS;
        const xxx = row.XXX;
        const dmtuid = row.DMTUID;

        if (!mpn || !tt || !ff || !cc || !ss || !xxx) {
          return; // Skip rows without proper DMT classification
        }

        // Build fields object based on template
        const familyKey = tt + ff;
        const templateFields = templates[familyKey] || [];
        const fields = {};

        for (const field of templateFields) {
          if (row[field] && row[field] !== '') {
            fields[field] = row[field];
          }
        }

        // Create component object
        const component = {
          mpn,
          dmtuid,
          tt,
          ff,
          cc,
          ss,
          xxx,
          manufacturer: row.Manufacturer || null,
          description: row.Description || null,
          datasheet: row.Datasheet || null,
          quantity: parseInt(row.Quantity) || 0,
          location: row.Location || null,
          value: row.Value || null,
          package_case: row['Package / Case'] || null,
          mounting_type: row['Mounting Type'] || null,
          operating_temperature: row['Operating Temperature'] || null,
          rohs: row.RoHS === 'YES',
          specifications: fields
        };

        components.push(component);
      })
      .on('end', async () => {
        console.log(`Found ${components.length} components in CSV`);

        // Insert in batches of 100
        const batchSize = 100;
        for (let i = 0; i < components.length; i += batchSize) {
          const batch = components.slice(i, i + batchSize);
          console.log(`Inserting batch ${Math.floor(i / batchSize) + 1}/${Math.ceil(components.length / batchSize)}...`);

          const { error } = await supabase
            .from('components')
            .upsert(batch, { onConflict: 'mpn' });

          if (error) {
            console.error(`Error inserting batch: ${error.message}`);
          }
        }

        console.log('CSV import completed!');
        resolve();
      })
      .on('error', reject);
  });
}

async function main() {
  try {
    await populateDMTHierarchy();
    await importCSVData();
    console.log('\nDatabase population complete!');
  } catch (error) {
    console.error('Error:', error);
    process.exit(1);
  }
}

main();
