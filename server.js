const fs = require('fs');
const https = require('https');
const path = require('path');
const express = require('express');

const app = express();
app.use(express.static(path.join(__dirname, 'public')));

// IMPORTANTE: Insira aqui o IP do seu notebook e os nomes dos arquivos do mkcert
const IP = '192.168.1.15'; // Substitua pelo IP da sua máquina
const options = {
  key: fs.readFileSync(`./${IP}-key.pem`),
  cert: fs.readFileSync(`./${IP}.pem`)
};

https.createServer(options, app).listen(8080, '0.0.0.0', () => {
  console.log(`\n🚀 MVP WebAR Rodando!`);
  console.log(`📱 No celular, acesse: https://${IP}:8080\n`);
});