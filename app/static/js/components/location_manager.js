export class LocationManager {
    async obtenerUbicacion() {
        return new Promise((resolve, reject) => {
            navigator.geolocation.getCurrentPosition(resolve, reject, { timeout: 10000 });
        });
    }
}