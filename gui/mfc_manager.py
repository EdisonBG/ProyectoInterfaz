class MFCGasManager:
    """
    Gestor centralizado para los gases de los MFCs.
    Coordina los cambios entre todas las ventanas.
    """
    
    def __init__(self):
        # Estado inicial de los gases
        self._gases = {
            1: "O2",  # mfc_1
            2: "CO2", # mfc_2  
            3: "N2",  # mfc_3
            4: "H2"   # mfc_4
        }
        
        # NUEVO: Gases actualmente en ejecución (para modo auto)
        self._gases_en_ejecucion = {
            1: "O2",
            2: "CO2", 
            3: "N2",
            4: "H2"
        }
        
        # Diccionario para callbacks: {mfc_id: [callback_functions]}
        self._callbacks = {1: [], 2: [], 3: [], 4: []}
        
        # NUEVO: Callbacks específicos para cambios de ejecución
        self._callbacks_ejecucion = {1: [], 2: [], 3: [], 4: []}
    
    def get_gas(self, mfc_id):
        """Obtiene el gas actual para un MFC"""
        return self._gases.get(mfc_id, "Unknown")
    
    def set_gas(self, mfc_id, gas):
        """Establece el gas para un MFC y notifica a todos los suscriptores"""
        if mfc_id in self._gases and gas != self._gases[mfc_id]:
            self._gases[mfc_id] = gas
            self._notify_all(mfc_id, gas)
    
    # NUEVOS MÉTODOS PARA GASES EN EJECUCIÓN
    def set_gas_en_ejecucion(self, mfc_id, gas):
        """Establece el gas en ejecución para modo auto"""
        if mfc_id in self._gases_en_ejecucion and gas != self._gases_en_ejecucion[mfc_id]:
            self._gases_en_ejecucion[mfc_id] = gas
            self._notify_ejecucion(mfc_id, gas)
    
    def get_gas_en_ejecucion(self, mfc_id):
        """Obtiene el gas actualmente en ejecución"""
        return self._gases_en_ejecucion.get(mfc_id, "Unknown")
    
    def register_callback(self, mfc_id, callback_function):
        """Registra una función callback para ser notificada cuando cambie el gas"""
        if mfc_id in self._callbacks:
            self._callbacks[mfc_id].append(callback_function)
    
    # NUEVO: Registrar callbacks para cambios de ejecución
    def register_callback_ejecucion(self, mfc_id, callback_function):
        """Registra una función callback para cambios de gas en ejecución"""
        if mfc_id in self._callbacks_ejecucion:
            self._callbacks_ejecucion[mfc_id].append(callback_function)
    
    def _notify_all(self, mfc_id, new_gas):
        """Notifica a todos los callbacks registrados para este MFC"""
        for callback in self._callbacks.get(mfc_id, []):
            try:
                callback(mfc_id, new_gas)
            except Exception as e:
                print(f"Error en callback para MFC {mfc_id}: {e}")
    
    # NUEVO: Notificar cambios de ejecución
    def _notify_ejecucion(self, mfc_id, new_gas):
        """Notifica a todos los callbacks de ejecución registrados"""
        for callback in self._callbacks_ejecucion.get(mfc_id, []):
            try:
                callback(mfc_id, new_gas)
            except Exception as e:
                print(f"Error en callback de ejecución para MFC {mfc_id}: {e}")

# Instancia global que compartirán todas las ventanas
mfc_gas_manager = MFCGasManager()