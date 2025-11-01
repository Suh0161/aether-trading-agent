import React from 'react'
import ReactDOM from 'react-dom/client'
import App from './App'
import './index.css'

// Epic ASCII Art
console.log(`
       .o.       oooooooooooo ooooooooooooo ooooo   ooooo oooooooooooo ooooooooo.   
     .888.      \`888'     \`8 8'   888   \`8 \`888'   \`888' \`888'     \`8 \`888   \`Y88. 
    .8"888.      888              888       888     888   888          888   .d88' 
   .8' \`888.     888oooo8         888       888ooooo888   888oooo8     888ooo88P'  
  .88ooo8888.    888    "         888       888     888   888    "     888\`88b.    
 .8'     \`888.   888       o      888       888     888   888       o  888  \`88b.  
o88o     o8888o o888ooooood8     o888o     o888o   o888o o888ooooood8 o888o  o888o 
                                                                                   
                                                                                   
                                                                                   
`);

ReactDOM.createRoot(document.getElementById('root')).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>
)
