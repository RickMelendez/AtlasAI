/**
 * Icon Generator for Atlas AI
 * Genera un icono de orb con efecto glow y partículas
 */

const { createCanvas } = require('canvas');
const fs = require('fs');
const path = require('path');

// Configuración del icono
const SIZE = 256;
const CENTER = SIZE / 2;
const ORB_RADIUS = 70;

/**
 * Crea un gradiente radial para el orb
 */
function createOrbGradient(ctx) {
  const gradient = ctx.createRadialGradient(CENTER, CENTER, 0, CENTER, CENTER, ORB_RADIUS);

  // Colores según CLAUDE.md
  gradient.addColorStop(0, '#00FFA3');    // Centro: green cyan
  gradient.addColorStop(0.3, '#00D9FF');  // Cyan brilliant
  gradient.addColorStop(0.6, '#7B2FFF');  // Purple
  gradient.addColorStop(1, '#FF006E');    // Pink en los bordes

  return gradient;
}

/**
 * Dibuja el efecto glow alrededor del orb
 */
function drawGlow(ctx) {
  // Glow exterior (más difuso)
  ctx.shadowColor = '#00D9FF';
  ctx.shadowBlur = 40;
  ctx.shadowOffsetX = 0;
  ctx.shadowOffsetY = 0;

  // Círculo para el glow
  ctx.beginPath();
  ctx.arc(CENTER, CENTER, ORB_RADIUS + 10, 0, Math.PI * 2);
  ctx.fillStyle = 'rgba(0, 217, 255, 0.3)';
  ctx.fill();
}

/**
 * Dibuja el orb principal
 */
function drawOrb(ctx) {
  // Reset shadow para el orb principal
  ctx.shadowBlur = 20;
  ctx.shadowColor = '#7B2FFF';

  // Orb con gradiente
  ctx.beginPath();
  ctx.arc(CENTER, CENTER, ORB_RADIUS, 0, Math.PI * 2);
  ctx.fillStyle = createOrbGradient(ctx);
  ctx.fill();

  // Highlight (brillo superior)
  const highlightGradient = ctx.createRadialGradient(
    CENTER - 20, CENTER - 20, 0,
    CENTER - 20, CENTER - 20, 40
  );
  highlightGradient.addColorStop(0, 'rgba(255, 255, 255, 0.6)');
  highlightGradient.addColorStop(1, 'rgba(255, 255, 255, 0)');

  ctx.beginPath();
  ctx.arc(CENTER - 20, CENTER - 20, 40, 0, Math.PI * 2);
  ctx.fillStyle = highlightGradient;
  ctx.fill();
}

/**
 * Dibuja partículas flotantes alrededor del orb
 */
function drawParticles(ctx) {
  ctx.shadowBlur = 10;

  const particles = [
    { x: CENTER - 90, y: CENTER - 30, size: 4, color: '#00D9FF' },
    { x: CENTER + 85, y: CENTER - 40, size: 3, color: '#7B2FFF' },
    { x: CENTER - 70, y: CENTER + 60, size: 5, color: '#FF006E' },
    { x: CENTER + 75, y: CENTER + 50, size: 4, color: '#00FFA3' },
    { x: CENTER - 50, y: CENTER - 80, size: 3, color: '#00D9FF' },
    { x: CENTER + 60, y: CENTER + 85, size: 3, color: '#7B2FFF' },
    { x: CENTER + 95, y: CENTER + 10, size: 2, color: '#00FFA3' },
    { x: CENTER - 100, y: CENTER + 20, size: 2, color: '#FF006E' },
  ];

  particles.forEach(particle => {
    ctx.shadowColor = particle.color;
    ctx.beginPath();
    ctx.arc(particle.x, particle.y, particle.size, 0, Math.PI * 2);
    ctx.fillStyle = particle.color;
    ctx.fill();
  });
}

/**
 * Genera el icono PNG
 */
function generateIcon() {
  console.log('🎨 Generando icono de Atlas AI...');

  // Crear canvas
  const canvas = createCanvas(SIZE, SIZE);
  const ctx = canvas.getContext('2d');

  // Fondo transparente (ya es por defecto)
  ctx.clearRect(0, 0, SIZE, SIZE);

  // Dibujar elementos
  drawGlow(ctx);
  drawOrb(ctx);
  drawParticles(ctx);

  // Guardar PNG
  const outputPath = path.join(__dirname, '../public/assets/icons/orb-icon.png');
  const buffer = canvas.toBuffer('image/png');
  fs.writeFileSync(outputPath, buffer);

  console.log('✅ Icono PNG generado:', outputPath);
  console.log('📏 Tamaño:', SIZE + 'x' + SIZE, 'px');
  console.log('🎨 Formato: PNG con transparencia');

  return outputPath;
}

/**
 * Genera versión ICO para Windows (usando sharp si está disponible)
 */
async function generateICO(pngPath) {
  try {
    const sharp = require('sharp');

    const icoPath = path.join(__dirname, '../public/assets/icons/orb-icon.ico');

    // Sharp no soporta ICO directamente, pero podemos crear múltiples tamaños PNG
    // Para ICO real, usa herramientas online o ImageMagick
    console.log('⚠️  Para generar ICO, usa una herramienta online:');
    console.log('   https://convertio.co/png-ico/');
    console.log('   O instala ImageMagick y ejecuta:');
    console.log('   magick convert orb-icon.png -define icon:auto-resize=256,128,64,48,32,16 orb-icon.ico');

  } catch (err) {
    console.log('ℹ️  Sharp no instalado. Solo se generó PNG.');
    console.log('   Para ICO, usa: https://convertio.co/png-ico/');
  }
}

// Ejecutar
try {
  const pngPath = generateIcon();
  generateICO(pngPath);

  console.log('\n🚀 ¡Icono generado exitosamente!');
  console.log('   Reinicia la app de Electron para ver el cambio.');

} catch (error) {
  console.error('❌ Error generando icono:', error.message);
  console.log('\n💡 Solución:');
  console.log('   Instala canvas con: npm install canvas --save-dev');
  process.exit(1);
}
