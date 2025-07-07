require('dotenv').config();
const CodaIntegration = require('./src/coda-integration');

async function testCodaIntegration() {
  console.log('Testing Coda Integration...\n');
  
  const coda = new CodaIntegration();
  
  // Check if Coda is configured
  if (!coda.isConfigured()) {
    console.log('❌ Coda not configured. Please add the following to your .env file:');
    console.log('CODA_API_TOKEN=your-coda-api-token-here');
    console.log('CODA_DOC_ID=your-coda-doc-id-here');
    console.log('CODA_TABLE_ID=your-coda-table-id-here');
    return;
  }
  
  console.log('✅ Coda configuration found');
  
  // Test table schema
  console.log('\n📋 Testing table schema...');
  const schema = await coda.getTableSchema();
  if (schema) {
    console.log('✅ Table schema retrieved successfully');
    console.log(`Table name: ${schema.name}`);
    console.log(`Columns: ${schema.displayColumn}, ${schema.rowCount} rows`);
  } else {
    console.log('❌ Failed to retrieve table schema');
  }
  
  // Test adding a response
  console.log('\n📝 Testing response storage...');
  const testUserId = 'test-user-123';
  const testResponse = '5';
  const testTimestamp = new Date().toISOString();
  
  const success = await coda.addResponse(testUserId, testResponse, testTimestamp);
  if (success) {
    console.log('✅ Test response stored successfully');
  } else {
    console.log('❌ Failed to store test response');
  }
  
  // Test retrieving responses
  console.log('\n📊 Testing response retrieval...');
  const responses = await coda.getResponses();
  console.log(`✅ Retrieved ${responses.length} responses from Coda`);
  
  console.log('\n🎉 Coda integration test completed!');
}

testCodaIntegration().catch(console.error); 