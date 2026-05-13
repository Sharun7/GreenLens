# Copyright (c) 2026 Sharun Tomy
# Licensed under BUSL-1.1. See LICENSE file for details.
# Commercial use prohibited without written permission.

"""
Management command to train MLP prediction model.

Usage:
    python manage.py train_mlp_model
    python manage.py train_mlp_model --retrain
"""
from django.core.management.base import BaseCommand
from ai_features.mlp_predictor import train_mlp_model, get_predictor


class Command(BaseCommand):
    help = "Train MLP model on existing PCRS data in database"
    
    def add_arguments(self, parser):
        parser.add_argument(
            "--retrain",
            action="store_true",
            help="Force retraining even if model already exists",
        )
    
    def handle(self, *args, **options):
        self.stdout.write(self.style.WARNING("Training MLP model on database..."))
        
        try:
            # Train model
            metrics = train_mlp_model()
            
            # Display results
            self.stdout.write(self.style.SUCCESS("\n" + "="*80))
            self.stdout.write(self.style.SUCCESS("MLP MODEL TRAINING COMPLETE"))
            self.stdout.write(self.style.SUCCESS("="*80))
            
            self.stdout.write(f"\nTraining Samples: {metrics['n_train']}")
            self.stdout.write(f"Test Samples: {metrics['n_test']}")
            self.stdout.write(f"Total Samples: {metrics['n_samples']}")
            
            self.stdout.write(f"\nTraining Metrics:")
            self.stdout.write(f"  R² Score: {metrics['train_r2']:.4f}")
            self.stdout.write(f"  MAE: {metrics['train_mae']:.2f}")
            self.stdout.write(f"  MSE: {metrics['train_mse']:.2f}")
            
            self.stdout.write(f"\nTest Metrics:")
            self.stdout.write(f"  R² Score: {metrics['test_r2']:.4f}")
            self.stdout.write(f"  MAE: {metrics['test_mae']:.2f}")
            self.stdout.write(f"  MSE: {metrics['test_mse']:.2f}")
            
            self.stdout.write(f"\nPrediction Variance: {metrics['training_variance']:.2f}")
            
            # Model quality assessment
            if metrics['test_r2'] >= 0.8:
                quality = "EXCELLENT"
                color = self.style.SUCCESS
            elif metrics['test_r2'] >= 0.6:
                quality = "GOOD"
                color = self.style.SUCCESS
            elif metrics['test_r2'] >= 0.4:
                quality = "FAIR"
                color = self.style.WARNING
            else:
                quality = "POOR"
                color = self.style.ERROR
            
            self.stdout.write(color(f"\nModel Quality: {quality}"))
            
            # Get model path
            predictor = get_predictor()
            self.stdout.write(f"\nModel saved to: {predictor.model_path}")
            
            self.stdout.write(self.style.SUCCESS("\n" + "="*80))
            self.stdout.write(self.style.SUCCESS("✓ Model ready for predictions"))
            self.stdout.write(self.style.SUCCESS("="*80 + "\n"))
        
        except ValueError as e:
            self.stdout.write(self.style.ERROR(f"\n✗ Training failed: {e}"))
            self.stdout.write(self.style.WARNING("\nMake sure you have:"))
            self.stdout.write("  1. At least 10 bonds with PCRS scores")
            self.stdout.write("  2. Climate hazard data for those bonds")
            self.stdout.write("\nRun these commands first:")
            self.stdout.write("  python manage.py score_all_bonds")
            self.stdout.write("  python manage.py fetch_climate_hazards\n")
        
        except Exception as e:
            self.stdout.write(self.style.ERROR(f"\n✗ Unexpected error: {e}"))
            import traceback
            traceback.print_exc()
